"""End-to-end agent audit against the fake SDK message stream (see tests/fake_query.py)."""

from pathlib import Path

from claude_agent_sdk import ResultError

from kb_librarian.agent.runner import run_agent_audit, run_offline_audit
from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.reports import ReportStore
from kb_librarian.tools.server import qualified
from tests.conftest import TODAY
from tests.fake_query import FakeQuery, _result, _settings

AKIA = "AKIAIOSFODNN7EXAMPLE"


def test_offline_audit_writes_report_with_planted_findings(kb_root: Path):
    report = run_offline_audit(_settings(), kb_root, today=TODAY)
    assert report.status == "completed" and report.dry_run is True
    assert {"frontmatter", "freshness", "links", "sensitive"} <= {f.check for f in report.findings}
    assert ReportStore(kb_root / ".librarian/reports").load(report.audit_id).audit_id == report.audit_id
    assert (kb_root / ".librarian/reports" / f"{report.audit_id}.md").exists()


def test_offline_audit_records_failure(kb_root: Path):
    (kb_root / "kb.config.yaml").write_text("version: 1\n")
    report = run_offline_audit(_settings(), kb_root, today=TODAY)
    assert report.status == "failed" and "ValidationError" in (report.error or "")


async def test_agent_audit_dry_run_denies_mutation_and_records_trail(kb_root: Path):
    fake = FakeQuery(
        calls=[
            ("run_checks", {}),
            (
                "set_frontmatter_field",
                {"path": "onboarding/stale.md", "field": "status", "value": "draft", "reason": "bump"},
            ),
            (
                "flag_for_review",
                {"path": "onboarding/stale.md", "reason": "owner must re-review", "severity": "warning"},
            ),
        ],
        result=_result(),
    )
    manager = AuditTaskManager()
    report = await run_agent_audit(_settings(), kb_root, dry_run=True, today=TODAY, query_fn=fake, manager=manager)
    assert report.status == "completed" and report.dry_run is True
    assert report.total_cost_usd == 0.0123 and report.num_turns == 3
    assert report.ai_summary == "Done: flagged the stale page."
    assert [(c.tool, c.ok) for c in report.tool_calls] == [
        ("run_checks", True),
        ("set_frontmatter_field", False),
        ("flag_for_review", True),
    ]
    assert "DRY RUN" in report.tool_calls[1].summary and fake.denied == ["set_frontmatter_field"]
    assert "status: active" in (kb_root / "docs/onboarding/stale.md").read_text()
    assert report.manual_review_needed[0].path == "onboarding/stale.md"
    assert fake.captured_options.max_turns == 5 and "DRY RUN" in fake.prompt
    assert "freshness" in fake.tool_results[0]["content"][0]["text"]
    assert AKIA not in (kb_root / ".librarian/reports" / f"{report.audit_id}.json").read_text()
    assert manager.running() == []


async def test_agent_audit_live_applies_and_logs_action(kb_root: Path):
    fake = FakeQuery(
        calls=[
            (
                "set_frontmatter_field",
                {"path": "onboarding/stale.md", "field": "status", "value": "draft", "reason": "unowned"},
            )
        ],
        result=_result(result=None),
    )
    report = await run_agent_audit(
        _settings(allow_live=True), kb_root, dry_run=False, capabilities=["frontmatter"], today=TODAY, query_fn=fake
    )
    assert report.dry_run is False and report.status == "completed"
    assert "status: draft" in (kb_root / "docs/onboarding/stale.md").read_text()
    assert report.fixes_applied[0].action_type == "set_frontmatter_field" and not report.fixes_applied[0].dry_run
    assert (kb_root / ".librarian/snapshots" / f"{report.fixes_applied[0].action_id}.before").exists()
    assert report.ai_summary == "Starting audit." and report.capabilities == ["frontmatter"]


async def test_agent_audit_records_sdk_permission_denials(kb_root: Path):
    denial = {"tool_name": qualified("regenerate_index"), "tool_use_id": "x", "tool_input": {}}
    fake = FakeQuery([], _result(permission_denials=[denial]))
    report = await run_agent_audit(_settings(), kb_root, today=TODAY, query_fn=fake)
    assert [(c.tool, c.ok) for c in report.tool_calls] == [("regenerate_index", False)]


async def test_agent_audit_error_result_and_exceptions_are_recorded(kb_root: Path):
    errored = await run_agent_audit(
        _settings(), kb_root, today=TODAY, query_fn=FakeQuery([], _result(is_error=True, subtype="error_max_turns"))
    )
    assert errored.status == "failed" and "error_max_turns" in (errored.error or "")
    crashed = await run_agent_audit(
        _settings(), kb_root, today=TODAY, query_fn=FakeQuery([], _result(), raise_after=RuntimeError("cli died"))
    )
    assert crashed.status == "failed" and "cli died" in (crashed.error or "")
    result_error = await run_agent_audit(
        _settings(),
        kb_root,
        today=TODAY,
        query_fn=FakeQuery([], _result(), raise_after=ResultError("budget", _result(is_error=True))),
    )
    assert result_error.status == "failed" and "budget" in (result_error.error or "")
    assert ReportStore(kb_root / ".librarian/reports").load(crashed.audit_id).status == "failed"


async def test_agent_audit_atlassian_factory_shares_the_report(kb_root: Path):
    from claude_agent_sdk import tool
    from mcp.types import ToolAnnotations

    from kb_librarian.tools.context import text_result

    def factory(ctx):
        @tool(
            name="external_note",
            description="d",
            input_schema={"reason": str},
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def external_note(args):
            ctx.record_external_action("external_note", "T-1", args["reason"])
            return text_result("ok")

        return [external_note]

    fake = FakeQuery([("external_note", {"reason": "track it"})], _result())
    report = await run_agent_audit(
        _settings(allow_live=True), kb_root, dry_run=False, today=TODAY, query_fn=fake, tool_factories=[factory]
    )
    assert [a.action_type for a in report.fixes_applied] == ["external_note"]
    dry = await run_agent_audit(
        _settings(),
        kb_root,
        today=TODAY,
        query_fn=FakeQuery([("external_note", {"reason": "r"})], _result()),
        tool_factories=[factory],
    )
    assert dry.fixes_applied == [] and dry.tool_calls[0].ok is False


async def test_agent_audit_cancel_marks_report_cancelled(kb_root: Path):
    manager = AuditTaskManager()

    class CancellingQuery(FakeQuery):
        async def __call__(self, *, prompt, options):
            manager.cancel(next(iter(manager.running())))
            async for message in super().__call__(prompt=prompt, options=options):
                yield message

    report = await run_agent_audit(
        _settings(),
        kb_root,
        today=TODAY,
        query_fn=CancellingQuery([("run_checks", {})], _result(result=None)),
        manager=manager,
    )
    assert report.status == "cancelled" and report.tool_calls == [] or report.tool_calls[0].ok is False


async def test_keyboard_interrupt_marks_report_cancelled(kb_root: Path):
    import pytest

    fake = FakeQuery([], _result(), raise_after=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        await run_agent_audit(_settings(), kb_root, today=TODAY, query_fn=fake)
    latest = ReportStore(kb_root / ".librarian/reports").latest()
    assert latest is not None and latest.status == "cancelled"
