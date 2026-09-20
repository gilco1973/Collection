"""Read endpoints: identity, contract, sections, pages, files, search, problem reports."""

import json
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from kb_librarian.agent.prompts import CAPABILITY_PROMPTS
from kb_librarian.api import service
from kb_librarian.api.deps import AppState, Principal, current_principal, get_state
from kb_librarian.catalog.catalog import Catalog
from kb_librarian.checks.sensitive import redact, withholds
from kb_librarian.models import new_id
from kb_librarian.retrieval.state import semantic_hits

router = APIRouter()
_REPORT_WINDOW_S, _REPORTS_PER_WINDOW = 60.0, 5
_recent_reports: dict[str, deque[float]] = defaultdict(deque)
_throttle_lock = threading.Lock()  # the route runs on threadpool workers
PROBLEM_CATEGORIES = ("outdated", "incorrect", "unclear", "broken-link", "sensitive-content", "other")


class ProblemReport(BaseModel):
    category: str = Field(pattern=f"^({'|'.join(PROBLEM_CATEGORIES)})$")
    message: str = Field(min_length=10, max_length=1000)


@router.get("/me")
def me(state: AppState = Depends(get_state), principal: Principal = Depends(current_principal)) -> dict:
    return {
        "role": principal.role,
        "live_allowed": state.settings.allow_live,
        "atlassian_configured": state.settings.atlassian_configured,
        "sso_configured": state.settings.sso_configured,
        "user": principal.user.as_dict() if principal.user else None,
        "operator_via": principal.via,
    }


@router.get("/contract")
def contract(state: AppState = Depends(get_state)) -> dict:
    return {
        **state.config.model_dump(),
        "capabilities": sorted(CAPABILITY_PROMPTS),
        "defaults": {"max_turns": state.settings.max_turns, "max_budget_usd": state.settings.max_budget_usd},
    }


def _title_overrides(state: AppState, catalog: Catalog, translated: set[str]) -> dict[str, str]:
    """Section id -> its README's translated title, for every section whose README was translated."""
    readmes = {s.id: f"{s.path}/README.md" for s in state.config.sections if f"{s.path}/README.md" in translated}
    return {section_id: doc.title for section_id, path in readmes.items() if (doc := catalog.get(path)) is not None}


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/sections")
def sections(lang: str | None = None, state: AppState = Depends(get_state)) -> list[dict]:
    catalog, translated = state.catalog_for(lang)
    return service.sections_overview(catalog, state.config, _title_overrides(state, catalog, translated))


@router.get("/sections/{section_id}/pages")
def section_pages(section_id: str, lang: str | None = None, state: AppState = Depends(get_state)) -> dict:
    if state.config.section_by_id(section_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no section '{section_id}'")
    catalog, _ = state.catalog_for(lang)
    withheld = service.withheld_paths(catalog, state.store.latest_completed())
    items = [service.page_summary(d, state.config) for d in catalog.in_section(section_id)]
    return {"items": [service.withheld_summary(s) if s["path"] in withheld else s for s in items]}


@router.get("/pages")
def pages(
    owner: str | None = None,
    stale: str | None = Query(default=None, pattern="^(true|false)$"),
    audience: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    lang: str | None = None,
    state: AppState = Depends(get_state),
) -> dict:
    """``audience`` (a reader's persona) is a listing filter like the others: every page stays reachable by path."""
    catalog, _ = state.catalog_for(lang)
    withheld = service.withheld_paths(catalog, state.store.latest_completed())
    filters = {"owner": owner, "stale": stale, "audience": audience}
    result = service.search(catalog, state.config, "", filters, withheld)
    return {"items": [{k: v for k, v in item.items() if k != "snippet"} for item in result["items"][:limit]]}


@router.get("/search")
def search_pages(
    request: Request,
    q: str = Query(default="", max_length=200),
    section: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    audience: str | None = None,
    owner: str | None = None,
    stale: str | None = Query(default=None, pattern="^(true|false)$"),
    lang: str | None = None,
    mode: str = Query(default="hybrid", pattern="^(keyword|semantic|hybrid)$"),
    state: AppState = Depends(get_state),
) -> dict:
    catalog, _ = state.catalog_for(lang)
    withheld = service.withheld_paths(catalog, state.store.latest_completed())
    filters = {"section": section, "status": status_, "audience": audience, "owner": owner, "stale": stale}
    retriever = state.retriever() if mode != "keyword" else None
    hits = semantic_hits(retriever, catalog, q, withheld, client=_client(request))  # per-client embed ceiling
    return service.search(catalog, state.config, q, filters, withheld, semantic=hits, mode=mode)


@router.get("/files/{path:path}", response_class=PlainTextResponse)
def catalog_file(path: str, state: AppState = Depends(get_state)) -> str:
    """Read-only access to the YAML catalogs (videos, resources) the contract lists."""
    if path not in {c.path for c in state.config.catalogs}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no catalog file '{path}'")
    docs_root = (state.root / state.config.docs_root).resolve()
    file: Path = docs_root / path
    if file.is_symlink() or docs_root not in file.resolve().parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no catalog file '{path}'")  # the scanner skips symlinks too
    if not file.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"catalog file '{path}' is missing")
    text = file.read_text(encoding="utf-8")
    if withholds(text.splitlines(), path):  # the same rule that withholds a page
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"catalog file '{path}' is withheld pending review")
    return text


@router.get("/pages/{path:path}/findings")
def page_findings(path: str, state: AppState = Depends(get_state)) -> dict:
    return {"items": [f.model_dump() for f in service.findings_for(state.store.latest_completed(), path)]}


@router.post("/pages/{path:path}/reports", status_code=status.HTTP_201_CREATED)
def report_problem(path: str, body: ProblemReport, request: Request, state: AppState = Depends(get_state)) -> dict:
    doc = state.catalog().get(path)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page at '{path}'")
    problems = state.root / ".librarian" / "problems"
    problems.mkdir(parents=True, exist_ok=True)
    _throttle(_client(request))
    if len(list(problems.glob("problem-*.json"))) >= state.settings.max_problem_reports:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "problem report queue is full; ask an owner to triage it"
        )
    problem_id = new_id("problem")
    record = {
        "id": problem_id,
        "path": path,
        "owner": doc.meta.get("owner"),
        "category": redact(body.category),
        "message": redact(body.message),
        "at": datetime.now(UTC).isoformat(),
    }
    (problems / f"{problem_id}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return {"id": problem_id, "owner": doc.meta.get("owner")}


@router.get("/pages/{path:path}")
def page(path: str, lang: str | None = None, state: AppState = Depends(get_state)) -> dict:
    catalog, translated = state.catalog_for(lang)
    doc = catalog.get(path)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page at '{path}'")
    withheld = doc.rel_path in service.withheld_paths(catalog, state.store.latest_completed())
    section_config = state.config.section_by_id(doc.section_id) if doc.section_id else None
    section = None
    if section_config:
        overrides = _title_overrides(state, catalog, translated)
        section = {"id": section_config.id, "title": overrides.get(section_config.id, section_config.title)}
    meta = service.page_summary(doc, state.config)
    return {
        "meta": service.withheld_summary(meta) if withheld else meta,
        "body_markdown": None if withheld else doc.body,
        "withheld": withheld,
        "section": section,
        "translated": False if withheld else doc.rel_path in translated,
    }


def _throttle(client: str) -> None:
    now = time.monotonic()
    with _throttle_lock:
        idle = [k for k, w in _recent_reports.items() if k != client and (not w or now - w[-1] > _REPORT_WINDOW_S)]
        for key in idle:
            del _recent_reports[key]  # buckets never outlive their window, whatever the number of clients
        window = _recent_reports[client]
        while window and now - window[0] > _REPORT_WINDOW_S:
            window.popleft()
        if len(window) >= _REPORTS_PER_WINDOW:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many problem reports; try again in a minute")
        window.append(now)
