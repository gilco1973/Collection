from pathlib import Path

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext
from claude_agent_sdk.types import _get_can_use_tool_shadowed_warning

from kb_librarian.agent.gate import GatePolicy, make_can_use_tool, make_pretooluse_gate
from kb_librarian.agent.hooks import build_hooks, response_summary
from kb_librarian.agent.options import DISALLOWED_BUILTINS, build_options
from kb_librarian.agent.prompts import DEFAULT_CAPABILITIES, build_initial_prompt
from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.tools.server import MUTATING_TOOLS, build_kb_server, build_kb_tools, mutating_names, qualified

ALLOWED = [qualified(n) for n in ("run_checks", "set_frontmatter_field", "flag_for_review")]
MUTATING = {"set_frontmatter_field", "regenerate_index"}
CTX = ToolPermissionContext()


def _policy(dry_run: bool) -> GatePolicy:
    return GatePolicy(dry_run, ALLOWED, MUTATING)


async def test_gate_denies_unknown_tools_in_every_mode():
    for dry_run in (True, False):
        result = await make_can_use_tool(_policy(dry_run))("Bash", {"command": "rm -rf /"}, CTX)
        assert isinstance(result, PermissionResultDeny) and "not a librarian tool" in result.message


async def test_gate_denies_mutating_tools_in_dry_run_and_allows_reads():
    gate = make_can_use_tool(_policy(True))
    denied = await gate(qualified("set_frontmatter_field"), {"reason": "x"}, CTX)
    assert isinstance(denied, PermissionResultDeny) and "DRY RUN" in denied.message
    assert isinstance(await gate(qualified("run_checks"), {}, CTX), PermissionResultAllow)
    assert isinstance(
        await gate(qualified("flag_for_review"), {"path": "p", "reason": "r"}, CTX), PermissionResultAllow
    )


async def test_gate_live_requires_reason_for_mutations():
    gate = make_can_use_tool(_policy(False))
    no_reason = await gate(qualified("set_frontmatter_field"), {"reason": "  "}, CTX)
    assert isinstance(no_reason, PermissionResultDeny) and "reason" in no_reason.message
    ok = await gate(qualified("set_frontmatter_field"), {"reason": "fix"}, CTX)
    assert isinstance(ok, PermissionResultAllow) and ok.updated_input == {"reason": "fix"}
    assert _policy(False).is_mutating(qualified("regenerate_index")) and not _policy(False).is_mutating("get_document")


async def test_pretooluse_gate_hook_records_denials():
    report = AuditReport(audit_type="agent")
    hook = make_pretooluse_gate(_policy(True), report)
    denied = await hook({"tool_name": qualified("set_frontmatter_field"), "tool_input": {"reason": "x"}}, "t1", None)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "DRY RUN" in denied["hookSpecificOutput"]["permissionDecisionReason"]
    unknown = await hook({"tool_name": "ToolSearch", "tool_input": {}}, "t2", None)
    assert unknown["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert await hook({"tool_name": qualified("run_checks"), "tool_input": {}}, "t3", None) == {}
    assert [(c.tool, c.ok) for c in report.tool_calls] == [("set_frontmatter_field", False), ("ToolSearch", False)]


def test_response_summary_handles_sdk_shapes():
    assert response_summary([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == (True, "a b")
    assert response_summary({"content": [{"type": "text", "text": "x"}], "isError": True}) == (False, "x")
    assert response_summary({"content": "bad", "is_error": True}) == (False, "bad")
    assert response_summary("plain") == (True, "plain")
    assert response_summary(None) == (True, "")


async def test_hooks_record_calls_failures_and_honour_cancel(tmp_path: Path):
    report = AuditReport(audit_type="agent")
    manager = AuditTaskManager(tmp_path / "cancel")
    manager.register(report.audit_id)
    hooks = build_hooks(report, manager, gate_hook=make_pretooluse_gate(_policy(True), report))
    assert len(hooks["PreToolUse"][0].hooks) == 2
    post = hooks["PostToolUse"][0].hooks[0]
    await post(
        {
            "tool_name": qualified("run_checks"),
            "tool_input": {"check": "links"},
            "tool_response": [{"type": "text", "text": "[]"}],
        },
        "tu1",
        None,
    )
    fail = hooks["PostToolUseFailure"][0].hooks[0]
    await fail({"tool_name": qualified("get_document"), "tool_input": {}, "error": "boom"}, "tu2", None)
    assert [(c.tool, c.ok) for c in report.tool_calls] == [("run_checks", True), ("get_document", False)]
    assert report.tool_calls[1].summary == "failed: boom"
    cancel_hook = hooks["PreToolUse"][0].hooks[1]
    assert await cancel_hook({"tool_name": "x"}, "tu4", None) == {}
    assert manager.cancel(report.audit_id) is True
    assert (await cancel_hook({"tool_name": "x"}, "tu5", None))["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (tmp_path / "cancel" / report.audit_id).exists()
    manager.unregister(report.audit_id)
    assert not (tmp_path / "cancel" / report.audit_id).exists() and manager.running() == []


def test_cancel_marker_is_visible_across_manager_instances(tmp_path: Path):
    first, second = AuditTaskManager(tmp_path / "c"), AuditTaskManager(tmp_path / "c")
    first.register("audit-1")
    assert second.cancel("audit-1") is True and first.is_cancelled("audit-1")
    assert AuditTaskManager().cancel("nobody") is False


def test_build_options_is_locked_down_and_never_shadows(tmp_path: Path):
    settings = LibrarianSettings(max_turns=7, max_budget_usd=0.5, model="claude-opus-5")
    server = build_kb_server([])
    options = build_options(settings, server, cwd=tmp_path, can_use_tool=make_can_use_tool(_policy(True)), hooks={})
    assert options.allowed_tools == [] and options.tools == []
    assert set(DISALLOWED_BUILTINS) <= set(options.disallowed_tools)
    assert options.max_turns == 7 and options.max_budget_usd == 0.5
    assert options.setting_sources == [] and options.strict_mcp_config is True
    assert options.permission_mode == "default" and options.mcp_servers == {"kb": server}
    assert _get_can_use_tool_shadowed_warning(options.permission_mode, options.allowed_tools) is None
    override = build_options(
        settings,
        server,
        cwd=tmp_path,
        can_use_tool=make_can_use_tool(_policy(True)),
        hooks={},
        max_turns=3,
        max_budget_usd=0.1,
    )
    assert override.max_turns == 3 and override.max_budget_usd == 0.1


def test_every_tool_declares_annotations_and_matches_the_documented_set(catalog, kb_root, kb_config):
    from kb_librarian.tools.context import ToolContext

    ctx = ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=AuditReport(audit_type="agent"))
    tools = build_kb_tools(ctx)
    derived = mutating_names(tools)
    assert derived == MUTATING_TOOLS - {"confluence_publish_page", "jira_create_issue"}
    assert "flag_for_review" not in derived


def test_initial_prompt_mentions_mode_and_capabilities():
    prompt = build_initial_prompt(True, list(DEFAULT_CAPABILITIES), "error links x: y", 10, 1.0)
    assert "DRY RUN" in prompt and "## Freshness" in prompt and "error links x: y" in prompt
    live = build_initial_prompt(False, ["atlassian"], "", 10, 1.0)
    assert "LIVE" in live and "## Atlassian" in live and "## Freshness" not in live
