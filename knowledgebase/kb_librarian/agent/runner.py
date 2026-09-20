"""The audit entry points: deterministic (offline) and agentic (Claude Agent SDK)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import date
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, ResultError, ResultMessage, SdkMcpTool, TextBlock, query

from kb_librarian.agent.gate import GatePolicy, make_can_use_tool, make_pretooluse_gate
from kb_librarian.agent.hooks import build_hooks
from kb_librarian.agent.options import build_options
from kb_librarian.agent.prompts import DEFAULT_CAPABILITIES, build_initial_prompt
from kb_librarian.agent.task_manager import AuditTaskManager, audit_task_manager
from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.checks import run_all_checks
from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.models import AuditReport, ToolCall
from kb_librarian.reports import ReportStore
from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.server import build_kb_server, build_kb_tools, mutating_names, qualified

logger = logging.getLogger(__name__)

QueryFn = Callable[..., AsyncIterator[Any]]
ToolFactory = Callable[[ToolContext], list[SdkMcpTool]]
_DIGEST_LIMIT = 15


def _store(settings: LibrarianSettings, root: Path) -> ReportStore:
    return ReportStore(root / settings.reports_dir)


def _context(root: Path, report: AuditReport, offline: bool, today: date | None) -> ToolContext:
    config = load_kb_config(root / "kb.config.yaml")
    ctx = ToolContext(root=root, config=config, catalog=load_catalog(root, config), report=report, offline=offline)
    if today is not None:
        ctx.today = today
    return ctx


def _digest(report: AuditReport) -> str:
    lines = [f"{f.severity} {f.check} {f.path}: {f.message}" for f in report.findings[:_DIGEST_LIMIT]]
    if len(report.findings) > _DIGEST_LIMIT:
        lines.append(f"... and {len(report.findings) - _DIGEST_LIMIT} more")
    return "\n".join(lines) or "no findings"


def run_offline_checks(root: Path, *, today: date | None = None, offline: bool = True) -> AuditReport:
    """Deterministic checks as an unsaved report (used by `check`, the CI gate)."""
    report = AuditReport(audit_type="offline", dry_run=True)
    try:
        ctx = _context(root, report, offline, today)
        report.findings = run_all_checks(ctx.catalog, ctx.config, today=ctx.today, offline=offline)
        report.finish("completed")
    except Exception as exc:  # noqa: BLE001 — the report must record the failure
        logger.exception("offline checks failed")
        report.finish("failed", error=f"{type(exc).__name__}: {exc}")
    return report


def run_offline_audit(
    settings: LibrarianSettings,
    root: Path,
    *,
    dry_run: bool = True,
    today: date | None = None,
    offline: bool = True,
    requested_by: str | None = None,
) -> AuditReport:
    """Run only the deterministic checks and persist the report."""
    report = run_offline_checks(root, today=today, offline=offline)
    report.dry_run = settings.resolve_dry_run(dry_run)
    report.requested_by = requested_by
    _store(settings, root).save(report)
    return report


def _apply_result(report: AuditReport, message: ResultMessage, texts: list[str]) -> None:
    report.total_cost_usd = float(message.total_cost_usd or 0.0)
    report.num_turns = int(message.num_turns or 0)
    report.ai_summary = message.result or (texts[-1] if texts else None)
    for denial in message.permission_denials or []:
        name = str(denial.get("tool_name", "")) if isinstance(denial, dict) else str(denial)
        if not any(c.tool == name.split("__")[-1] and not c.ok for c in report.tool_calls):
            report.tool_calls.append(
                ToolCall(tool=name.split("__")[-1], ok=False, summary="denied (reported by the SDK)")
            )
    if message.is_error:
        report.finish("failed", error=f"agent result error: {message.subtype}")


async def run_agent_audit(
    settings: LibrarianSettings,
    root: Path,
    *,
    dry_run: bool = True,
    capabilities: list[str] | None = None,
    offline: bool = True,
    today: date | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    tool_factories: list[ToolFactory] | None = None,
    query_fn: QueryFn = query,
    manager: AuditTaskManager = audit_task_manager,
    reason: str | None = None,
    requested_by: str | None = None,
    on_registered: Callable[[str], None] | None = None,
) -> AuditReport:
    """Run the deterministic checks, then let the librarian agent work the findings.

    ``tool_factories`` build extra tools (Atlassian) against the audit's own context
    so their actions land in this report. ``query_fn`` is the SDK ``query`` by default;
    tests inject a fake stream so the loop, gate and hooks run without a network call.
    """
    caps = list(capabilities or DEFAULT_CAPABILITIES)
    report = AuditReport(
        audit_type="agent",
        dry_run=settings.resolve_dry_run(dry_run),
        capabilities=caps,
        reason=reason,
        requested_by=requested_by,
    )
    store = _store(settings, root)
    if manager.cancel_dir is None:
        manager.configure(root)
    manager.register(report.audit_id)
    store.save(report)  # visible to `reports list` and `cancel` while it runs
    if on_registered is not None:
        on_registered(report.audit_id)
    try:
        # The deterministic phase is CPU and network bound; keep it off the event loop.
        ctx = await asyncio.to_thread(_context, root, report, offline, today)
        report.findings = await asyncio.to_thread(
            run_all_checks, ctx.catalog, ctx.config, today=ctx.today, offline=offline
        )
        tools = build_kb_tools(ctx)
        for factory in tool_factories or []:
            tools.extend(factory(ctx))
        policy = GatePolicy(report.dry_run, [qualified(t.name) for t in tools], mutating_names(tools))
        options = build_options(
            settings,
            build_kb_server(tools),
            cwd=root,
            can_use_tool=make_can_use_tool(policy),
            hooks=build_hooks(
                report, manager, gate_hook=make_pretooluse_gate(policy, report), mutating=policy.mutating
            ),
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
        )
        prompt = build_initial_prompt(
            report.dry_run, caps, _digest(report), options.max_turns or 0, options.max_budget_usd or 0.0
        )
        texts: list[str] = []
        try:
            async for message in query_fn(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    texts.extend(b.text for b in message.content if isinstance(b, TextBlock))
                elif isinstance(message, ResultMessage):
                    _apply_result(report, message, texts)
        except ResultError as exc:
            if report.status == "in_progress":
                report.finish("failed", error=f"agent result error: {exc}")
        if report.status == "in_progress":
            report.finish("cancelled" if manager.is_cancelled(report.audit_id) else "completed")
    except (asyncio.CancelledError, KeyboardInterrupt):
        report.finish("cancelled", error="interrupted by the operator")
        raise
    except Exception as exc:  # noqa: BLE001 — the report must record the failure
        logger.exception("agent audit failed")
        report.finish("failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        manager.unregister(report.audit_id)
        store.save(report)
    return report
