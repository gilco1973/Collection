"""Run one chat turn: a short, read-only, tool-using agent call grounded in the knowledge base.

No write tools are even offered (not just gated): ``build_read_tools`` is the whole tool set, so
there is nothing a chat turn could mutate. The permission gate and audit-trail hooks still run,
for the same defence-in-depth reason ``agent/options.py`` locks down the built-in tools.
"""

import math
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultError, ResultMessage, TextBlock
from claude_agent_sdk import query as sdk_query

from kb_librarian.agent.gate import GatePolicy, make_can_use_tool, make_pretooluse_gate
from kb_librarian.agent.hooks import build_hooks
from kb_librarian.agent.options import DISALLOWED_BUILTINS
from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.catalog.catalog import Catalog, load_catalog
from kb_librarian.chat.prompts import CHAT_SYSTEM_PROMPT, ChatContext, ChatTurn, build_chat_prompt
from kb_librarian.chat.quiz import parse_quiz
from kb_librarian.config import LibrarianSettings
from kb_librarian.i18n.localize import localize
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.models import AuditReport
from kb_librarian.retrieval.state import retriever_for
from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.read_tools import build_read_tools
from kb_librarian.tools.server import KB_SERVER_NAME, build_kb_server, mutating_names, qualified

QueryFn = Callable[..., AsyncIterator[Any]]
MAX_HISTORY_TURNS = 8


@dataclass
class ChatAnswer:
    answer: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    quiz: list[dict] | None = None  # ``mode="quiz"`` only: validated questions, and then ``answer`` is empty
    cost_usd: float | None = None  # ``ResultMessage.total_cost_usd``: what the turn was billed, error or not


def _cost(message: ResultMessage) -> float | None:
    """What the SDK billed for the turn; only a finite, non-negative number is worth recording."""
    cost = message.total_cost_usd
    return float(cost) if isinstance(cost, int | float) and math.isfinite(cost) and cost >= 0 else None


def _readable(catalog: Catalog) -> Catalog:
    """The catalog minus every page the API withholds from readers: the chat answers readers, so
    the model must not be able to read (and paraphrase) a page they may not open themselves."""
    readable = [d for d in catalog.documents if not d.sensitive]
    return Catalog(root=catalog.root, docs_root=catalog.docs_root, documents=readable)


def _sources_from_trail(report: AuditReport, catalog: Catalog) -> list[dict[str, str]]:
    """Pages the agent actually read (``get_document``), not merely surfaced by a search."""
    paths: list[str] = []
    for call in report.tool_calls:
        if call.ok and call.tool == "get_document":
            path = str(call.input.get("path", ""))
            if path and path not in paths:
                paths.append(path)
    sources = []
    for path in paths:
        doc = catalog.get(path)
        if doc is not None:
            sources.append({"path": doc.rel_path, "title": doc.title})
    return sources


async def run_chat(
    settings: LibrarianSettings,
    root: Path,
    message: str,
    history: list[ChatTurn],
    *,
    lang: str | None = None,
    mode: str = "ask",
    context: ChatContext | None = None,
    query_fn: QueryFn = sdk_query,
) -> ChatAnswer:
    config = load_kb_config(root / "kb.config.yaml")
    localized = bool(lang and lang in config.i18n.languages)

    def view(full: Catalog) -> Catalog:
        readable = _readable(full)
        return localize(readable, root / config.docs_root, str(lang))[0] if localized else readable

    catalog = view(load_catalog(root, config))
    if context is not None and catalog.get(context.path) is None:
        return ChatAnswer(error=f"no readable page at '{context.path}'")  # the API checks first; this is the backstop
    report = AuditReport(audit_type="offline", dry_run=True, capabilities=["chat"])
    # ``semantic_search`` is offered only when an index was built; its hits are limited to ``catalog`` (the view).
    ctx = ToolContext(
        root=root, config=config, catalog=catalog, report=report, offline=True, view=view,
        retriever=retriever_for(root, settings),
    )  # fmt: skip
    tools = build_read_tools(ctx)
    policy = GatePolicy(True, [qualified(t.name) for t in tools], mutating_names(tools))
    options = ClaudeAgentOptions(
        system_prompt=CHAT_SYSTEM_PROMPT,
        mcp_servers={KB_SERVER_NAME: build_kb_server(tools)},
        tools=[],
        allowed_tools=[],
        disallowed_tools=list(DISALLOWED_BUILTINS),
        permission_mode="default",
        can_use_tool=make_can_use_tool(policy),
        hooks=build_hooks(
            report, AuditTaskManager(), gate_hook=make_pretooluse_gate(policy, report), mutating=policy.mutating
        ),
        max_turns=settings.chat_max_turns,
        max_budget_usd=settings.chat_max_budget_usd,
        model=settings.model,
        effort=settings.effort,
        cwd=str(root),
        setting_sources=[],
        strict_mcp_config=True,
    )
    prompt = build_chat_prompt(history[-MAX_HISTORY_TURNS:], message, mode=mode, context=context)
    texts: list[str] = []
    result_text: str | None = None
    cost: float | None = None
    try:
        async for msg in query_fn(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                texts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
            elif isinstance(msg, ResultMessage):
                cost = _cost(msg)
                if msg.is_error:
                    return ChatAnswer(error=f"agent result error: {msg.subtype}", cost_usd=cost)
                result_text = msg.result or (texts[-1] if texts else None)
    except ResultError as exc:
        return ChatAnswer(error=f"agent result error: {exc}", cost_usd=cost)
    answer = (result_text or "").strip()
    if not answer:
        return ChatAnswer(error="the librarian returned no answer", cost_usd=cost)
    sources = _sources_from_trail(report, catalog)
    if mode != "quiz":
        return ChatAnswer(answer=answer, sources=sources, cost_usd=cost)
    try:
        return ChatAnswer(quiz=parse_quiz(answer), sources=sources, cost_usd=cost)
    except ValueError as exc:
        return ChatAnswer(error=f"the librarian returned a malformed quiz: {exc}", cost_usd=cost)
