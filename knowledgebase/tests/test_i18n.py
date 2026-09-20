"""kb_librarian/i18n: the translate call, change detection, and the sync writer."""

from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.i18n.localize import localize
from kb_librarian.i18n.sync import TranslationJob, content_hash, load_state, plan, sync
from kb_librarian.i18n.translate import TranslationError, translate_markdown
from kb_librarian.models import AuditReport

MARKED = "---TITLE---\nInicio\n---BODY---\n# Inicio\n\nContenido traducido.\n"


def _query(text: str):
    async def query_fn(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text=text)], model="fake")

    return query_fn


async def test_translate_markdown_parses_the_marked_reply():
    captured = {}

    async def query_fn(*, prompt, options):
        captured["prompt"] = prompt
        yield AssistantMessage(content=[TextBlock(text=MARKED)], model="fake")

    title, body = await translate_markdown("Onboarding", "# Onboarding\n\nBody.\n", "es", query_fn=query_fn)
    assert title == "Inicio" and body == "# Inicio\n\nContenido traducido.\n"
    assert "Spanish" in captured["prompt"]


async def test_translate_markdown_rejects_a_reply_without_markers():
    with pytest.raises(TranslationError):
        await translate_markdown("T", "B", "es", query_fn=_query("just some prose, no markers"))


async def test_translate_markdown_rejects_an_empty_title():
    text = "---TITLE---\n\n---BODY---\nSome body.\n"
    with pytest.raises(TranslationError):
        await translate_markdown("T", "B", "es", query_fn=_query(text))


def test_content_hash_changes_with_title_or_body():
    base = content_hash("Title", "Body")
    assert base == content_hash("Title", "Body")
    assert base != content_hash("Title 2", "Body")
    assert base != content_hash("Title", "Body 2")


def test_plan_skips_pages_with_no_frontmatter_or_sensitive_content(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    jobs = plan(catalog, ["es", "he"], {})
    by_path = {j.doc.rel_path for j in jobs}
    assert "governance/README.md" not in by_path  # no frontmatter
    assert "onboarding/stale.md" not in by_path  # planted AWS key: sensitive
    assert {j.lang for j in jobs if j.doc.rel_path == "onboarding/README.md"} == {"es", "he"}


def test_plan_skips_a_page_already_translated_at_its_current_hash(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    doc = catalog.get("onboarding/README.md")
    state = {"onboarding/README.md": {"es": content_hash(doc.title, doc.body)}}
    jobs = plan(catalog, ["es"], state)
    assert "onboarding/README.md" not in {j.doc.rel_path for j in jobs if j.lang == "es"}


def test_plan_retranslates_once_the_source_changes(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    state = {"onboarding/README.md": {"es": "stale-hash-from-before-the-edit"}}
    jobs = plan(catalog, ["es"], state)
    assert "onboarding/README.md" in {j.doc.rel_path for j in jobs if j.lang == "es"}


async def test_sync_writes_the_translated_file_and_advances_state(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    doc = catalog.get("onboarding/README.md")
    jobs = [TranslationJob(doc=doc, lang="es", hash=content_hash(doc.title, doc.body))]
    report = AuditReport(audit_type="offline", dry_run=False)

    results = await sync(kb_root, kb_config, jobs, report, query_fn=_query(MARKED))

    assert [r.status for r in results] == ["written"]
    written = (kb_root / "docs/i18n/es/onboarding/README.md").read_text(encoding="utf-8")
    assert "title: Inicio" in written and "owner: enablement" in written and "Contenido traducido." in written
    state = load_state(kb_root, kb_config)
    assert state["onboarding/README.md"]["es"] == jobs[0].hash
    assert len(report.fixes_applied) == 1 and report.fixes_applied[0].dry_run is False


async def test_sync_dry_run_writes_nothing_but_still_proposes(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    doc = catalog.get("onboarding/README.md")
    jobs = [TranslationJob(doc=doc, lang="es", hash=content_hash(doc.title, doc.body))]
    report = AuditReport(audit_type="offline", dry_run=True)

    results = await sync(kb_root, kb_config, jobs, report, query_fn=_query(MARKED))

    assert [r.status for r in results] == ["proposed"]
    assert not (kb_root / "docs/i18n/es/onboarding/README.md").exists()
    assert load_state(kb_root, kb_config) == {}
    assert report.fixes_applied[0].dry_run is True


async def test_sync_records_a_failure_without_stopping_the_batch(kb_root: Path, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    readme, stale = catalog.get("onboarding/README.md"), catalog.get("onboarding/stale.md")
    jobs = [TranslationJob(doc=readme, lang="es", hash="h1"), TranslationJob(doc=stale, lang="es", hash="h2")]
    report = AuditReport(audit_type="offline", dry_run=False)
    replies = iter(["not marked at all", MARKED])

    async def query_fn(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text=next(replies))], model="fake")

    results = await sync(kb_root, kb_config, jobs, report, query_fn=query_fn)

    assert [r.status for r in results] == ["failed", "written"]
    assert results[0].error and "markers" in results[0].error
    assert (kb_root / "docs/i18n/es/onboarding/stale.md").exists()


def _write_translation(kb_root: Path, lang: str, rel_path: str, title: str, body: str) -> None:
    target = kb_root / "docs/i18n" / lang / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\ntitle: {title}\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
        f"tags: [onboarding]\naudience: [new-hire]\n---\n{body}\n",
        encoding="utf-8",
    )


def test_localize_swaps_title_and_body_where_a_translation_exists(kb_root: Path, kb_config):
    _write_translation(kb_root, "es", "onboarding/README.md", "Inicio", "# Inicio\n\nContenido.")
    catalog = load_catalog(kb_root, kb_config)
    localized, translated = localize(catalog, kb_root / "docs", "es")
    assert translated == {"onboarding/README.md"}
    doc = localized.get("onboarding/README.md")
    assert doc.title == "Inicio" and "Contenido." in doc.body
    assert doc.meta["owner"] == "enablement"  # governance fields untouched
    assert doc.section_id == catalog.get("onboarding/README.md").section_id  # identity preserved
    # an untouched page keeps its English text and is not reported as translated
    assert localized.get("index.md").title == catalog.get("index.md").title
    assert "index.md" not in translated


def test_localize_falls_back_to_english_for_a_translation_missing_a_title(kb_root: Path, kb_config):
    target = kb_root / "docs/i18n/es/onboarding/README.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\nowner: enablement\n---\n# No title here\n", encoding="utf-8")
    catalog = load_catalog(kb_root, kb_config)
    localized, translated = localize(catalog, kb_root / "docs", "es")
    assert "onboarding/README.md" not in translated
    assert localized.get("onboarding/README.md").title == catalog.get("onboarding/README.md").title


def test_localize_ignores_a_symlinked_translation_file(kb_root: Path, kb_config):
    real = kb_root / "docs/real-secret.md"
    real.write_text("---\ntitle: Nope\n---\nshould never be read as a translation\n", encoding="utf-8")
    link_dir = kb_root / "docs/i18n/es/onboarding"
    link_dir.mkdir(parents=True)
    (link_dir / "README.md").symlink_to(real)
    catalog = load_catalog(kb_root, kb_config)
    localized, translated = localize(catalog, kb_root / "docs", "es")
    assert "onboarding/README.md" not in translated
    assert localized.get("onboarding/README.md").title == catalog.get("onboarding/README.md").title


def test_translated_pages_never_reach_the_english_catalog(kb_root: Path, kb_config):
    (kb_root / "docs/i18n/es/onboarding").mkdir(parents=True)
    (kb_root / "docs/i18n/es/onboarding/README.md").write_text(
        "---\ntitle: Inicio\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
        "tags: [onboarding]\naudience: [new-hire]\n---\n# Inicio\n",
        encoding="utf-8",
    )
    catalog = load_catalog(kb_root, kb_config)
    assert catalog.get("i18n/es/onboarding/README.md") is None
    assert all(not d.rel_path.startswith("i18n/") for d in catalog.documents)
