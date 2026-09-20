"""Detect new/modified pages and (re)translate them: the nightly job.

Change detection is a content hash per (page, language) kept in a small state file
under ``docs/i18n/.state.json`` — not git — so the same logic works locally, in CI, or
from a cron job on the deployed box. Writes go through the same ``ActionLog`` audits
use, so a bad machine translation is a normal rollback.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import query as sdk_query

from kb_librarian.actions import ActionLog
from kb_librarian.catalog.catalog import Catalog, Document
from kb_librarian.catalog.frontmatter import render_frontmatter
from kb_librarian.i18n.translate import QueryFn, translate_markdown
from kb_librarian.kbconfig import KbConfig
from kb_librarian.models import AuditReport
from kb_librarian.tools.context import SNAPSHOTS_DIR

STATE_FILE = "i18n/.state.json"


def content_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\x00{body}".encode()).hexdigest()


def load_state(root: Path, config: KbConfig) -> dict[str, dict[str, str]]:
    path = root / config.docs_root / STATE_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(root: Path, config: KbConfig, state: dict[str, dict[str, str]]) -> None:
    path = root / config.docs_root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class TranslationJob:
    doc: Document
    lang: str
    hash: str


def plan(catalog: Catalog, languages: list[str], state: dict[str, dict[str, str]]) -> list[TranslationJob]:
    """Every (page, language) pair whose source has no translation yet, or has changed since its last one."""
    jobs = []
    for doc in catalog.documents:
        if doc.frontmatter_error or not doc.has_frontmatter or doc.sensitive:
            continue  # nothing sound to translate, or content that must not reach an LLM at all
        current = content_hash(doc.title, doc.body)
        for lang in languages:
            if state.get(doc.rel_path, {}).get(lang) != current:
                jobs.append(TranslationJob(doc=doc, lang=lang, hash=current))
    return jobs


@dataclass
class TranslationResult:
    rel_path: str
    lang: str
    status: str  # "written" | "proposed" | "failed"
    error: str | None = None


async def sync(
    root: Path,
    config: KbConfig,
    jobs: list[TranslationJob],
    report: AuditReport,
    *,
    model: str | None = None,
    query_fn: QueryFn = sdk_query,
) -> list[TranslationResult]:
    """Translate every job and write it through ``ActionLog`` (a no-op on disk in dry-run).

    One failing page is recorded and skipped rather than aborting the whole run — a nightly
    job should still translate everything it can.
    """
    docs_root = root / config.docs_root
    actions = ActionLog(docs_root, report, root / SNAPSHOTS_DIR)
    state = load_state(root, config)
    results: list[TranslationResult] = []
    for job in jobs:
        target_rel = f"i18n/{job.lang}/{job.doc.rel_path}"
        try:
            title, body = await translate_markdown(
                job.doc.title, job.doc.body, job.lang, model=model, query_fn=query_fn
            )
            meta = {**job.doc.meta, "title": title}
            existing = docs_root / target_rel
            expected = existing.read_text(encoding="utf-8") if existing.is_file() else None
            actions.write_page(
                "translate",
                target_rel,
                render_frontmatter(meta, body),
                f"machine-translated from {job.doc.rel_path} ({job.lang})",
                expected_text=expected,
            )
            if not report.dry_run:
                state.setdefault(job.doc.rel_path, {})[job.lang] = job.hash
            results.append(TranslationResult(job.doc.rel_path, job.lang, "proposed" if report.dry_run else "written"))
        except Exception as exc:  # noqa: BLE001 — one bad page must not stop the run; it's recorded and reported
            results.append(TranslationResult(job.doc.rel_path, job.lang, "failed", f"{type(exc).__name__}: {exc}"))
    if not report.dry_run:
        save_state(root, config, state)
    return results
