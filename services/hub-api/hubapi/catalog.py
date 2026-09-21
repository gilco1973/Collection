"""The catalog a person sees: the bank's own listings from the consumers file plus every component of the
collection from collection.json, access resolved per person from their entitlements, never from a role typed
by an owner (PLT-UI-17). The workspace and the shelf's sign-off view are here too."""
from __future__ import annotations
import json
from .auth import Principal

ROLES = ("owner", "ai_security")


class Catalog:
    def __init__(self, consumers: dict, collection: dict):
        self.c, self.col = consumers, collection
        self.bank = list(consumers.get("listings", []))
        self.details = {**consumers.get("details", {}), **collection.get("details", {})}
        self.all = self.bank + list(collection.get("listings", []))
        self.shelf = list(collection.get("shelf", []))

    @classmethod
    def load(cls, consumers_file: str, collection_file: str) -> "Catalog":
        return cls(json.load(open(consumers_file, encoding="utf-8")), json.load(open(collection_file, encoding="utf-8")))

    def resolve(self, l: dict, p: Principal) -> dict:
        if l.get("collection"):
            return l
        return {**l, "access": "open" if l["id"] in p.entitlements else ("request" if l["access"] == "open" else l["access"])}

    def catalog_for(self, p: Principal) -> dict:
        ids = self.c.get("availableIds") or [l["id"] for l in self.bank if l.get("kind") in ("assistant", "agent", "knowledge")][:4]
        available = [self.resolve(l, p) for l in self.bank if l["id"] in ids]
        listings = [self.resolve(l, p) for l in self.all]
        counts = {"all": len([l for l in self.bank if l["kind"] != "road"]), **{k: len([l for l in self.all if l["kind"] == kind]) for k, kind in
                  (("assistants", "assistant"), ("agents", "agent"), ("knowledge", "knowledge"), ("tools", "tool"), ("roads", "road"))}}
        return {"availableCount": len(available), "available": available, "listings": listings, "counts": counts,
                "changes": self.c.get("changes", []), "suggestions": self.c.get("suggestions", [])}

    def search(self, p: Principal, q: str) -> list[dict]:
        q = q.lower()
        return [l for l in self.catalog_for(p)["listings"] if q in f"{l['name']} {l['description']} {l['road']} {l['kind']}".lower()]

    def consumer(self, slug: str, p: Principal) -> dict | None:
        summary = next((l for l in self.all if l["slug"] == slug), None)
        if not summary:
            return None
        d = self.details.get(slug)
        you = "L0" if p.ladder == "L0" else (d or {}).get("youActAt", "L1")
        if d:
            return {**d, "youActAt": you, "access": self.resolve(d, p)["access"] if not summary.get("collection") else d["access"]}
        kind = summary["kind"]
        return {**summary, "crumbs": ["Discover", {"agent": "Agents", "assistant": "Assistants"}.get(kind, "Catalog"), summary["name"]], "youActAt": you, "ladderMax": "L1",
                "headerChips": summary.get("meta", []), "access": self.resolve(summary, p)["access"], "tiles": [], "does": [summary["description"]],
                "catalog": {"name": "—", "signed": False, "entries": []}, "trust": [], "evidence": [], "cost": [], "getStarted": [], "owner": [], "versions": [], "changelogHref": "#"}

    def workspace_for(self, p: Principal, briefs: list[dict]) -> dict:
        def _name_of(b: dict):
            uc = b.get("content", {}).get("useCase")
            return uc.get("name") if isinstance(uc, dict) else None
        draft = next((b for b in briefs if b["status"] == "draft" and b["createdBy"] == p.id), None)
        w = self.c.get("workspace", {})
        assistants = [a for a in w.get("assistants", []) if a["consumerId"] in p.entitlements]
        team_ids = {t["id"] for t in p.teams}
        team_consumers = [dict(tc) for tc in w.get("teamConsumers", []) if tc.get("teamId") in team_ids]
        for tc in team_consumers: tc.pop("teamId", None)
        if draft:
            team_consumers.append({"id": "brief-" + draft["id"], "name": (_name_of(draft) or "new use case").lower().replace(" ", "-"), "status": {"text": "proposed", "kind": "line"},
                                   "step": 1, "stepNote": "step 1 · brief in draft", "pipe": ["on", "", "", "", "", "", ""], "note": f"filed by you · {len(draft['completed']) + 1} of 6 sections", "briefId": draft["id"]})
        usage = dict(w.get("usage", {"sandboxMonth": "not measured", "sandboxNote": "shown back, not charged", "productionNote": "", "playgroundToday": "not measured", "playgroundBudget": "", "playgroundPct": 0}))
        usage["productionNote"] = usage.get("productionNote") or f"charged back to cost centre {p.costCentre}"
        return {"header": {"name": p.name, "role": "ops.lead" if "ops.lead" in p.roles else (p.roles[0] if p.roles else "employee"), "team": p.teams[0]["id"] if p.teams else "no team", "costCentre": p.costCentre},
                "assistants": assistants, "teamConsumers": team_consumers, "requests": [], "usage": usage, "playground": w.get("playground", {"gateway": "", "keyMasked": "", "fixtures": "", "example": ""})}

    # ---------------- the shelf ----------------
    def may_sign(self, r: dict, p: Principal, role: str) -> bool:
        if role == "owner":
            return bool(r.get("owner")) and r["owner"].lower() == p.handle
        return role == "ai_security" and "ai.security" in p.roles

    def shelf_entry(self, r: dict, p: Principal, recorded: list[dict]) -> dict:
        rec = {s["role"]: s for s in recorded if s["component"] == r["name"] and s["version"] == r["version"]}
        return {**r, "recorded": rec, "youMaySign": [role for role in ROLES if self.may_sign(r, p, role)]}

    def shelf_record(self, name: str) -> dict | None:
        return next((r for r in self.shelf if r["name"] == name), None)
