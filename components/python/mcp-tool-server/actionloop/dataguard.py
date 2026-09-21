"""Data guard.

Provenance: split a brief (ticket title, description, epic text, comments) into instruction segments tagged
with author id, display name and role. The ticket's reporter is treated as its author: title, description and
the reporter's own comments are the brief. Text from anyone else (role "other") taints the session with that
author as the source, and the assignee must confirm it before code is written. This implementation trusts the
reporter because the ticket's assignment is the claim and the reporter is the ticket's author. Masking: PII classes masked per audience
(model, log, human). Scoring: a cheap injection heuristic on upstream text that raises taint above a
threshold. Projection: a result projected to the declared shape before it reaches the model; a field declared "id" in the shape is kept verbatim (identifiers are not text).
"""
from __future__ import annotations
import html, re
from dataclasses import dataclass, field

PII_PATTERNS = {  # the most specific shapes first: a social security number is not a phone number
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "account": re.compile(r"\b\d{8,17}\b"),
    "phone": re.compile(r"\+?\d[\d\s().-]{8,}\d"),
}
INJECTION_MARKERS = (
    "ignore previous", "ignore all previous", "disregard", "you are now", "system prompt", "run the following",
    "curl ", "wget ", "rm -rf", "&& ", "| sh", "push to main", "print the token", "print your", "reveal", "exfiltrate",
)


@dataclass(frozen=True)
class Segment:
    text: str
    author_id: str
    author_display: str
    role: str  # assignee | reporter | groomer | other
    origin: str  # title | description | epic | comment:<id>


@dataclass
class Provenance:
    segments: list
    tainted: bool
    sources: list  # author ids that taint

    def foreign(self) -> list:
        return [s for s in self.segments if s.role == "other"]


def tag_brief(ticket: dict, assignee_id: str, groomer_ids: set[str] | None = None) -> Provenance:
    """ticket: {key,title,description,reporter_id,assignee_id,epic_text?,comments:[{id,author_id,author_display,body}]}"""
    groomer_ids = groomer_ids or set()

    def role(aid: str) -> str:
        if aid == assignee_id: return "assignee"
        if aid in groomer_ids: return "groomer"
        if aid == ticket.get("reporter_id"): return "reporter"
        return "other"

    segs = [Segment(ticket["title"], ticket["reporter_id"], ticket.get("reporter_display", ticket["reporter_id"]), role(ticket["reporter_id"]), "title"),
            Segment(ticket.get("description", ""), ticket["reporter_id"], ticket.get("reporter_display", ticket["reporter_id"]), role(ticket["reporter_id"]), "description")]
    if ticket.get("epic_text"):
        segs.append(Segment(ticket["epic_text"], ticket.get("epic_author_id", "epic"), "epic", role(ticket.get("epic_author_id", "epic")), "epic"))
    for c in ticket.get("comments", []):
        segs.append(Segment(c["body"], c["author_id"], c.get("author_display", c["author_id"]), role(c["author_id"]), f"comment:{c['id']}"))
    sources = sorted({s.author_id for s in segs if s.role == "other" and s.text.strip()})
    return Provenance(segs, bool(sources), sources)


KEEP = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?|\b\d{8}\.\d+\b")  # ISO dates and yyyymmdd.r run names: evidence, not PII


def mask(text: str, audience: str) -> tuple[str, list]:
    """Mask PII for the audience. model: replace with class tokens; log: hash-like stubs; human: keep last 4.
    Timestamps and pipeline run names are kept: a first read is about when things happened."""
    found = []
    kept: list[str] = []
    out = KEEP.sub(lambda m: (kept.append(m.group(0)), f"\x00{len(kept) - 1}\x00")[1], text)
    for cls, pat in PII_PATTERNS.items():
        def rep(m):
            found.append(cls)
            v = m.group(0)
            if audience == "model": return f"[{cls.upper()}]"
            if audience == "log": return f"[{cls}:***]"
            return f"[{cls}:…{v[-4:]}]"
        out = pat.sub(rep, out)
    out = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], out)
    return out, found


def injection_score(text: str) -> float:
    t = text.lower()
    hits = sum(1 for m in INJECTION_MARKERS if m in t)
    return min(1.0, hits / 3.0)


def fence(segments: list, audience: str = "model") -> str:
    """Render the brief for the model with delimiting and a provenance header per segment. Bodies and attributes
    are escaped: a ticket cannot close the fence and open a forged one, a display name cannot inject an attribute."""
    parts = []
    for i, s in enumerate(segments):
        body, _ = mask(s.text, audience)
        parts.append(f"<segment id=\"{i}\" origin=\"{_esc(s.origin)}\" author=\"{_esc(s.author_display)}\" role=\"{_esc(s.role)}\">\n{_esc(body)}\n</segment>")
    return "\n".join(parts)


def _esc(v) -> str:
    return html.escape(str(v), quote=True)


def project(raw: dict, shape: dict) -> dict:
    """Keep only the declared fields; drop everything else before classification ."""
    return {k: raw[k] for k in shape if k in raw}


@dataclass
class GuardResult:
    projected: dict
    masked_for_model: dict
    pii_classes: list
    score: float
    taint: bool


def _walk(v, classes: list, score: list):
    """Every string at any depth is masked and scored: a nested object or a list of strings never reaches the model raw."""
    if isinstance(v, str):
        m, f = mask(v, "model"); classes += f; score[0] = max(score[0], injection_score(v)); return m
    if isinstance(v, dict):
        return {k: _walk(x, classes, score) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk(x, classes, score) for x in v]
    return v


def after_call(raw: dict, shape: dict, threshold: float = 0.34) -> GuardResult:
    p = project(raw, shape)
    masked, classes, score = {}, [], [0.0]
    for k, v in p.items():
        if shape.get(k) == "id":
            masked[k] = v; continue   # an identifier field (channel id, URL, key): never text, never masked, never scored
        masked[k] = _walk(v, classes, score)
    return GuardResult(p, masked, sorted(set(classes)), score[0], score[0] >= threshold)
