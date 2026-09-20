"""The intake brief's rules, the same as the browser's schema (hub/src/api/schemas.ts): six sections, §7.11 step 1.

Validation returns field errors keyed by dotted path, the shape the API returns for 422 and the form renders.
The messages are for the person filling the form.
"""
from __future__ import annotations
import re, time, uuid

CHANNELS, TIERS, CEILINGS, CLASSES, NEEDS = ("operator", "customer", "partner", "batch"), ("R", "W1", "W2", "M"), ("R", "W1", "W2"), ("internal", "confidential", "restricted"), ("none", "utility", "workhorse", "frontier")
TIER_RANK = {"R": 0, "W1": 1, "W2": 2, "M": 3}
STEPS = ("useCase", "people", "dataAndTools", "model", "outcome", "review")


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def validate_step(step: str, v) -> dict:
    e: dict[str, list] = {}
    add = lambda k, m: e.setdefault(f"{step}.{k}", []).append(m)
    v = v if isinstance(v, dict) else {}
    if step == "useCase":
        n = _s(v.get("name"))
        if len(n) < 3: add("name", "Give the use case a name.")
        if len(n) > 80: add("name", "Keep the name under 80 characters.")
        if len(_s(v.get("problem"))) < 20: add("problem", "Describe what happens today in a few sentences.")
        if v.get("channel") not in CHANNELS: add("channel", "Choose a channel.")
        if not _s(v.get("teamId")): add("teamId", "Choose the team this belongs to.")
    elif step == "people":
        if not _s(v.get("businessOwner")): add("businessOwner", "Name the business owner.")
        if not _s(v.get("productOwner")): add("productOwner", "Name the product owner.")
        if not _s(v.get("domainExpert")): add("domainExpert", "Name the domain expert who will label cases (PLT-ONB-11).")
        h = _num(v.get("labellingHoursPerWeek"))
        if h is None: add("labellingHoursPerWeek", "Enter hours per week.")
        elif h < 1: add("labellingHoursPerWeek", "At least one hour a week through sandbox.")
        elif h > 40: add("labellingHoursPerWeek", "That is more than a working week.")
    elif step == "dataAndTools":
        systems, tools, classes = v.get("systems") or [], v.get("tools") or [], v.get("dataClasses") or []
        if not systems: add("systems", "Name at least one system of record.")
        if not tools: add("tools", "Add at least one tool.")
        if len(tools) > 15: add("tools", "Over the 15-tool session ceiling; remove tools or split the consumer.")
        if not classes: add("dataClasses", "Choose the data classes the consumer reads.")
        if "restricted" in classes: add("dataClasses", "Restricted data is not available to a first consumer.")
        ceiling = v.get("tierCeiling")
        if ceiling not in CEILINGS: add("tierCeiling", "Choose a tier ceiling.")
        else:
            over = [t for t in tools if isinstance(t, dict) and TIER_RANK.get(t.get("tier"), 9) > TIER_RANK[ceiling]]
            if over: add("tierCeiling", "The tier ceiling must cover every tool: " + ", ".join(f"{t.get('name')} ({t.get('tier')})" for t in over) + ".")
        for t in tools:
            if not isinstance(t, dict) or not t.get("name") or t.get("tier") not in TIERS or not t.get("classes"): add("tools", "Each tool needs a name, a tier and its data classes."); break
    elif step == "model":
        if v.get("need") not in NEEDS: add("need", "Choose what the model needs to be.")
        if v.get("classificationCeiling") not in CLASSES: add("classificationCeiling", "Choose the classification ceiling.")
        if not isinstance(v.get("substitute"), bool): add("substitute", "Say whether a substitute model is acceptable.")
    elif step == "outcome":
        if not _s(v.get("metric")): add("metric", "Name one outcome metric (PLT-ONB-10).")
        if not _s(v.get("unit")): add("unit", "Give the metric a unit.")
        b, t = _num(v.get("baseline")), _num(v.get("target"))
        if b is None: add("baseline", "Enter today's figure.")
        elif b < 0: add("baseline", "A baseline cannot be negative.")
        if t is None: add("target", "Enter the target.")
        elif t < 0: add("target", "A target cannot be negative.")
        if b is not None and t is not None and b == t: add("target", "The target should differ from the baseline.")
        if not _s(v.get("measuredOn")): add("measuredOn", "When was the baseline measured?")
    elif step == "review":
        if v.get("acknowledged") is not True: add("acknowledged", "Confirm you have read what happens next.")
    return e


def validate(content: dict) -> dict:
    out: dict[str, list] = {}
    for step in STEPS:
        out.update(validate_step(step, (content or {}).get(step)))
    return out


def new_brief(principal) -> dict:
    now = _iso()
    return {"id": "brf_" + uuid.uuid4().hex[:6], "status": "draft", "etag": 'W/"1"', "createdBy": principal.id, "createdAt": now, "updatedAt": now, "currentStep": "useCase", "completed": [],
            "content": {"useCase": {"name": "", "problem": "", "channel": "operator", "teamId": principal.teams[0]["id"] if principal.teams else ""},
                        "people": {"businessOwner": "", "productOwner": principal.name, "domainExpert": "", "labellingHoursPerWeek": 0},
                        "dataAndTools": {"systems": [], "tools": [], "dataClasses": ["internal"], "tierCeiling": "R"},
                        "model": {"need": "workhorse", "classificationCeiling": "internal", "substitute": False},
                        "outcome": {"metric": "", "unit": "", "baseline": 0, "target": 0, "measuredOn": ""}, "review": {"acknowledged": False}}}


def bump(etag: str) -> str:
    n = int(re.sub(r"\D", "", etag) or 0) + 1
    return 'W/"%d"' % n


def estimate(base: dict, content: dict) -> dict:
    tools = len(((content or {}).get("dataAndTools") or {}).get("tools") or []) or 3
    need = ((content or {}).get("model") or {}).get("need", "workhorse")
    factor = {"frontier": 2.4, "utility": 0.4, "none": 0}.get(need, 1)
    classes = ((content or {}).get("dataAndTools") or {}).get("dataClasses") or []
    return {**base, "modelSpendMonthly": round(70 * tools * factor), "reviewHours": 6 if "confidential" in classes else 3}


def road(base: dict, content: dict) -> dict:
    ceiling = ((content or {}).get("dataAndTools") or {}).get("tierCeiling", "R")
    channel = ((content or {}).get("useCase") or {}).get("channel", "operator")
    if channel in ("customer", "partner"):
        return {**base, "road": "R3", "title": "Customer and partner assistant", "subtitle": "federated identity · entitlements · step-up", "selfService": False,
                "note": "R3 opens in Phase 5. The platform lead confirms the brief and Compliance reviews the channel templates."}
    if channel == "batch":
        return {**base, "road": "R4", "title": "Batch agent with a review queue", "subtitle": "drafts for a human · ladder L1", "selfService": True,
                "note": "Every output lands in a review queue; a sampling rule keeps a person on at least 5 percent of drafts."}
    if ceiling != "R":
        return {**base, "title": f"Write profile ({ceiling}) on road R2", "subtitle": "agent with tools · confirmation or dual control", "selfService": False,
                "note": "A write profile needs the platform lead's confirmation of the brief, and the second line reviews the delta before staging."}
    return dict(base)


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
