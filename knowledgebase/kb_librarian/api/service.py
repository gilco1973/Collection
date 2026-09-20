"""Read-model helpers behind the API: page summaries, search, findings, withholding."""

from collections import Counter
from datetime import date, timedelta
from typing import Any

from kb_librarian.catalog.catalog import Catalog, Document
from kb_librarian.checks.freshness import review_window
from kb_librarian.checks.frontmatter_check import parse_reviewed
from kb_librarian.checks.sensitive import WITHHOLD_SEVERITIES, redact
from kb_librarian.kbconfig import KbConfig
from kb_librarian.models import AuditReport, Finding
from kb_librarian.retrieval.index import Hit
from kb_librarian.retrieval.retriever import rrf

_SNIPPET = 160
FACETS = ("section", "status", "owner", "audience")


def next_review(doc: Document, config: KbConfig) -> date | None:
    reviewed = parse_reviewed(doc.meta.get("reviewed"))
    return None if reviewed is None else reviewed + timedelta(days=review_window(doc, config))


def page_summary(doc: Document, config: KbConfig, today: date | None = None) -> dict[str, Any]:
    due = next_review(doc, config)
    today = today or date.today()
    tags = doc.meta.get("tags") or []
    audience = doc.meta.get("audience") or []
    return {
        "path": doc.rel_path,
        "title": doc.title,
        "section": doc.section_id,
        "owner": doc.meta.get("owner"),
        "status": doc.meta.get("status"),
        "reviewed": str(doc.meta.get("reviewed") or ""),
        "next_review": due.isoformat() if due else None,
        "stale": bool(due and due < today and doc.meta.get("status") != "deprecated"),
        "tags": tags if isinstance(tags, list) else [tags],
        "audience": audience if isinstance(audience, list) else [audience],
        "frontmatter_error": doc.frontmatter_error,
    }


def snippet(doc: Document, query: str) -> str:
    body = doc.body
    index = body.lower().find(query.lower())
    start = 0 if index < 0 else max(0, index - _SNIPPET // 3)
    return body[start : start + _SNIPPET].replace("\n", " ")


def has_sensitive_content(doc: Document) -> bool:
    """Verdict on the page's current text, computed once per catalog load."""
    return doc.sensitive


def withheld_paths(catalog: Catalog, report: AuditReport | None) -> set[str]:
    """Pages whose content must not be exposed: flagged by the latest audit OR by their current text."""
    flagged = {
        f.path
        for f in (report.findings if report else [])
        if f.check == "sensitive" and f.severity in WITHHOLD_SEVERITIES
    }
    return flagged | {d.rel_path for d in catalog.documents if d.sensitive}


def readable_page(catalog: Catalog, report: AuditReport | None, path: str) -> Document | None:
    """The page at ``path`` when a reader may open it: it exists and is not withheld. Routes that
    must never confirm a withheld page exists (profile views, quiz results, chat context) answer
    404 on ``None`` for both cases alike."""
    doc = catalog.get(path)
    if doc is None or doc.rel_path in withheld_paths(catalog, report):
        return None
    return doc


def withheld_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """A withheld page's metadata with every string passed through the redactor (title, owner, tags...)."""
    return {
        key: redact(value)
        if isinstance(value, str) and key != "path"
        else [redact(v) for v in value]
        if isinstance(value, list)
        else value
        for key, value in summary.items()
    }


def _matches(doc: Document, query: str, withheld: set[str]) -> bool:
    """A withheld page never matches a query: even its title would be a substring oracle."""
    if doc.rel_path in withheld:
        return False
    needle = query.lower()
    return needle in doc.title.lower() or needle in doc.body.lower()


def _passes(summary: dict[str, Any], filters: dict[str, str | None], skip: str | None = None) -> bool:
    for key in ("section", "status", "owner"):
        if key != skip and filters.get(key) and summary[key] != filters[key]:
            return False
    if skip != "audience" and filters.get("audience") and filters["audience"] not in summary["audience"]:
        return False
    return not (filters.get("stale") in ("true", "false") and summary["stale"] != (filters["stale"] == "true"))


def _facet(summaries: list[dict[str, Any]], key: str, selected: str | None) -> list[dict[str, Any]]:
    values = (
        Counter(a for s in summaries for a in s["audience"])
        if key == "audience"
        else Counter(s[key] for s in summaries if s[key])
    )
    if selected and selected not in values:
        values[selected] = 0
    return [{"value": value, "count": count} for value, count in sorted(values.items())]


def _order(catalog: Catalog, query: str, withheld: set[str], semantic: list[Hit] | None, mode: str) -> list[str]:
    """Page paths in result order: the keyword order (catalog order of the matches), the semantic order,
    or their reciprocal-rank fusion. A withheld or unknown page in the semantic list is dropped here too —
    the index query already excluded it, and no caller can widen that."""
    keyword = [d.rel_path for d in catalog.documents if not query or _matches(d, query, withheld)]
    if semantic is None:
        return keyword
    ranked = [h.path for h in semantic if h.path not in withheld and catalog.get(h.path) is not None]
    return ranked if mode == "semantic" else rrf(keyword, ranked)


def search(
    catalog: Catalog,
    config: KbConfig,
    query: str,
    filters: dict[str, str | None],
    withheld: set[str] | None = None,
    semantic: list[Hit] | None = None,
    mode: str = "keyword",
) -> dict[str, Any]:
    """``semantic`` is the retriever's order for ``query`` (``None``: nothing semantic happened, so the
    effective mode is ``keyword`` whatever was asked); ``mode`` is echoed as the effective mode."""
    withheld = withheld or set()
    mode = mode if semantic is not None else "keyword"
    excerpts = {h.path: h.excerpt for h in reversed(semantic or [])}  # the best (first) chunk per page wins
    docs = [doc for path in _order(catalog, query, withheld, semantic, mode) if (doc := catalog.get(path))]
    by_path = {d.rel_path: d for d in docs}
    # Filters and items only ever see the redacted metadata of a withheld page (no confirmation oracle).
    summaries = [withheld_summary(s) if s["path"] in withheld else s for s in (page_summary(d, config) for d in docs)]
    items = [
        {
            **s,
            "snippet": None if s["path"] in withheld else snippet(by_path[s["path"]], query),
            "excerpt": excerpts.get(s["path"]),
        }
        for s in summaries
        if _passes(s, filters)
    ]
    # Each facet is computed with its own filter removed, so a chosen value never hides its alternatives;
    # withheld pages never contribute values (their owner/tags may be the sensitive content).
    visible = [s for s in summaries if s["path"] not in withheld]
    facets = {
        key: _facet([s for s in visible if _passes(s, filters, skip=key)], key, filters.get(key)) for key in FACETS
    }
    return {"items": items, "total": len(items), "facets": facets, "mode": mode}


def sections_overview(
    catalog: Catalog, config: KbConfig, title_overrides: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """``title_overrides`` (section id -> title) lets a localized request show a section's title as
    its translated README's title; omitted, every section keeps its English ``kb.config.yaml`` title."""
    overrides = title_overrides or {}
    out = []
    for section in config.sections:
        pages = [page_summary(d, config) for d in catalog.in_section(section.id)]
        out.append(
            {
                "id": section.id,
                "path": section.path,
                "title": overrides.get(section.id, section.title),
                "owner": section.owner,
                "review_every_days": section.review_every_days,
                "page_count": len(pages),
                "stale_count": sum(1 for p in pages if p["stale"]),
            }
        )
    return out


def findings_for(report: AuditReport | None, path: str) -> list[Finding]:
    return [f for f in report.findings if f.path == path] if report else []
