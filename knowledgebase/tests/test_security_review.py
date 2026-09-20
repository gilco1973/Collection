"""kb_librarian/security: registry, content versions and the sign-off ledger."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kb_librarian.security.ledger import latest_signoff, load_signoffs, module_status, record_signoff, sheet_with_row
from kb_librarian.security.registry import compute_version, load_registry
from tests.security_fixtures import SHEET, TABLE, make_project, signoff


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path)


def test_version_covers_code_scope_and_sheet_prose_but_not_signoff_rows(project: Path):
    module = load_registry(project).get("demo")
    before = compute_version(project, module)
    assert len(before.version) == 64 and before.short == before.version[:12]
    assert [f for f, _ in before.files] == ["pkg/a.py", "pkg/b.py"]
    sheet = project / "security" / "modules" / "demo.md"
    sheet.write_text(sheet.read_text() + "| abc | - | R | s | 2026-09-18 | approved | - |\n")
    assert compute_version(project, module).version == before.version  # a sign-off row never moves the version
    sheet.write_text(sheet.read_text().replace("Demo.", "Demo, now claiming more."))
    prose_changed = compute_version(project, module).version
    assert prose_changed != before.version  # what the sheet claims is part of what was signed
    registry = project / "security" / "registry.yaml"
    registry.write_text(registry.read_text().replace("paths: [pkg/]", "paths: [pkg/a.py]"))
    assert compute_version(project, load_registry(project).get("demo")).version != prose_changed  # scope shrink
    (project / "pkg" / "a.py").write_text("print('changed')\n")
    assert compute_version(project, load_registry(project).get("demo")).version not in (before.version, prose_changed)


def test_registry_rejects_bad_shapes_and_unsafe_patterns(project: Path):
    registry = project / "security" / "registry.yaml"
    original = registry.read_text()
    registry.write_text(original + "  - {id: demo, title: D, kind: backend, paths: [pkg/], sheet: x.md}\n")
    with pytest.raises(ValueError, match="unique"):
        load_registry(project)
    registry.write_text(original.replace("paths: [pkg/]", "paths: [nothing/]"))
    with pytest.raises(ValueError, match="matches no files"):
        compute_version(project, load_registry(project).get("demo"))
    registry.write_text(original.replace("sheet: security/modules/demo.md", "sheet: security/modules/none.md"))
    with pytest.raises(ValueError, match="no review sheet"):
        compute_version(project, load_registry(project).get("demo"))
    for pattern in ("../outside/", "/etc/passwd"):
        registry.write_text(original.replace("paths: [pkg/]", f"paths: ['{pattern}']"))
        with pytest.raises(ValueError, match="inside the project"):
            load_registry(project)
    registry.write_text(original.replace("version: 1", "version: 2"))
    with pytest.raises(ValueError, match="unsupported version"):
        load_registry(project)


def test_symlinks_and_files_outside_the_project_are_never_hashed(project: Path, tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1\n")
    (project / "pkg" / "link.py").symlink_to(outside / "secret.py")
    (project / "pkg" / "linkdir").symlink_to(outside, target_is_directory=True)
    files = [f for f, _ in compute_version(project, load_registry(project).get("demo")).files]
    assert files == ["pkg/a.py", "pkg/b.py"]


def test_signoff_is_bound_to_the_current_version_and_drift_is_detected(project: Path):
    module = load_registry(project).get("demo")
    current = compute_version(project, module)
    assert module_status(project, current) == ("unsigned", None)
    record_signoff(project, current, signoff(current.version, signature="sig|1"))
    assert module_status(project, current)[0] == "approved"
    sheet = (project / "security" / "modules" / "demo.md").read_text()
    assert f"| {current.short} | - | R | sig\\|1 | 2026-09-18 | approved | - |" in sheet
    assert load_signoffs(project, "demo")[0].version == current.version
    (project / "pkg" / "a.py").write_text("print('changed')\n")
    assert module_status(project, compute_version(project, module))[0] == "changed"
    with pytest.raises(ValueError, match="not the current version"):
        record_signoff(project, compute_version(project, module), signoff(current.version))


def test_latest_signoff_is_by_timestamp_not_file_order(project: Path):
    current = compute_version(project, load_registry(project).get("demo"))
    newer = signoff(current.version, "rejected")
    older = signoff(current.version, "approved")
    older.recorded_at = datetime(2020, 1, 1, tzinfo=UTC)
    record_signoff(project, current, newer)
    record_signoff(project, current, older)  # appended last, but recorded earlier
    assert latest_signoff(project, "demo").decision == "rejected"


def test_sheet_row_lands_in_the_signoff_table_only_and_a_bad_sheet_leaves_no_ledger(project: Path):
    current = compute_version(project, load_registry(project).get("demo"))
    entry = signoff(current.version)
    with_appendix = SHEET + "\n" + TABLE + "\n## Appendix\n\n| k | v |\n| --- | --- |\n| a | 1 |\n"
    out = sheet_with_row(with_appendix, entry)
    assert out.index(current.short) < out.index("## Appendix") and out.endswith("| a | 1 |\n")
    assert sheet_with_row(SHEET, entry).count("| Version |") == 1  # the table is created when missing
    sheet = project / "security" / "modules" / "demo.md"
    sheet.write_text(SHEET.replace("## Sign-off", "## Sign-off history") + "| x |\n")
    with pytest.raises(ValueError, match="Sign-off"):
        record_signoff(project, current, entry)
    assert not (project / "security" / "signoffs").exists()
