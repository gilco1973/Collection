"""Mutating tools. Every one records an action; in dry-run none touches disk.

The permission gate in ``agent/gate.py`` already denies these in dry-run; the
checks here are defence in depth so a misconfigured gate cannot mutate either.
"""

import json

from claude_agent_sdk import SdkMcpTool, tool
from mcp.types import ToolAnnotations

from kb_librarian.catalog.catalog import Document, render_index
from kb_librarian.catalog.frontmatter import render_frontmatter
from kb_librarian.kbconfig import KbConfig
from kb_librarian.tools.context import ToolContext, schema, text_result

MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
REPORT_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_OWNER_ONLY_FIELDS = frozenset({"reviewed"})


def _mode(ctx: ToolContext) -> str:
    return "DRY RUN — proposed, not written" if ctx.dry_run else "applied"


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def validate_field(config: KbConfig, field: str, value) -> str | None:
    """Return why ``field=value`` is not allowed, or ``None``. Only contract fields may be set."""
    allowed = set(config.frontmatter.required) | {"review_every_days"}
    if field in _OWNER_ONLY_FIELDS:
        return f"'{field}' may only be changed by the page owner"
    if field not in allowed:
        return f"'{field}' is not a contract field ({sorted(allowed)})"
    if field == "status" and value not in config.frontmatter.status_values:
        return f"status must be one of {config.frontmatter.status_values}"
    if field == "audience" and any(a not in config.frontmatter.audience_values for a in _as_list(value)):
        return f"audience values must be in {config.frontmatter.audience_values}"
    if field == "tags" and any(t not in config.taxonomy.tags for t in _as_list(value)):
        return "every tag must be in the taxonomy"
    if field == "review_every_days" and (not isinstance(value, int) or value <= 0):
        return "review_every_days must be a positive integer"
    return None


def _source(doc: Document) -> str:
    """The text the catalog loaded; a page that changed on disk since is refused (no lost update)."""
    return doc.raw


def build_write_tools(ctx: ToolContext) -> list[SdkMcpTool]:
    @tool(
        name="set_frontmatter_field",
        description=(
            "Set one contract frontmatter field on a page (status, owner, tags as a JSON list, audience, "
            "review_every_days). 'reviewed' is owner-only. Requires a reason."
        ),
        input_schema={"path": str, "field": str, "value": str, "reason": str},
        annotations=MUTATING,
    )
    async def set_frontmatter_field(args: dict) -> dict:
        doc = ctx.catalog.get(str(args.get("path", "")))
        if doc is None:
            return text_result(f"no page at '{args.get('path')}'", is_error=True)
        if doc.frontmatter_error:
            return text_result(
                f"{doc.rel_path} has invalid frontmatter ({doc.frontmatter_error}); flag it for review", is_error=True
            )
        if not doc.has_frontmatter:
            return text_result(f"{doc.rel_path} has no frontmatter; use add_frontmatter", is_error=True)
        field, raw = str(args["field"]), str(args["value"])
        try:
            value = json.loads(raw) if raw[:1] in "[{" or raw.isdigit() else raw
        except json.JSONDecodeError:
            value = raw
        problem = validate_field(ctx.config, field, value)
        if problem:
            return text_result(problem, is_error=True)
        meta = dict(doc.meta)
        meta[field] = value
        try:
            action = ctx.actions.write_page(
                "set_frontmatter_field",
                doc.rel_path,
                render_frontmatter(meta, doc.body),
                f"{field}={value!r}: {args.get('reason', '')}",
                expected_text=_source(doc),
            )
        except ValueError as exc:
            return text_result(str(exc), is_error=True)
        ctx.reload()
        return text_result(f"{_mode(ctx)}: {action.action_id} set {field} on {doc.rel_path}")

    @tool(
        name="add_frontmatter",
        description="Add a complete frontmatter block to a page that has none (fields: JSON object of contract fields)",
        input_schema={"path": str, "fields": str, "reason": str},
        annotations=MUTATING,
    )
    async def add_frontmatter(args: dict) -> dict:
        doc = ctx.catalog.get(str(args.get("path", "")))
        if doc is None:
            return text_result(f"no page at '{args.get('path')}'", is_error=True)
        if doc.has_frontmatter or doc.frontmatter_error or _source(doc).lstrip("﻿ \n").startswith("---"):
            return text_result(f"{doc.rel_path} already starts with a frontmatter block", is_error=True)
        try:
            fields = json.loads(str(args.get("fields", "{}")))
        except json.JSONDecodeError as exc:
            return text_result(f"fields is not valid JSON: {exc}", is_error=True)
        if not isinstance(fields, dict):
            return text_result("fields must be a JSON object", is_error=True)
        for name, value in fields.items():
            problem = None if name == "reviewed" else validate_field(ctx.config, name, value)
            if problem:
                return text_result(problem, is_error=True)
        try:
            action = ctx.actions.write_page(
                "add_frontmatter",
                doc.rel_path,
                render_frontmatter(fields, doc.body),
                str(args.get("reason", "")),
                expected_text=_source(doc),
            )
        except ValueError as exc:
            return text_result(str(exc), is_error=True)
        ctx.reload()
        return text_result(f"{_mode(ctx)}: {action.action_id} added frontmatter to {doc.rel_path}")

    @tool(
        name="regenerate_index",
        description="Regenerate docs/index.md from the catalog so every page is reachable.",
        input_schema={"reason": str},
        annotations=MUTATING,
    )
    async def regenerate_index(args: dict) -> dict:
        ctx.reload()
        existing = ctx.catalog.get("index.md")
        action = ctx.actions.write_page(
            "regenerate_index",
            "index.md",
            render_index(ctx.catalog, ctx.config, today=ctx.today),
            str(args.get("reason", "")),
            expected_text=_source(existing) if existing else None,
        )
        ctx.reload()
        return text_result(f"{_mode(ctx)}: {action.action_id} regenerated index.md")

    @tool(
        name="flag_for_review",
        description=(
            "Put a page on the human review queue when a fix needs an owner's judgement "
            "(stale content, policy questions, anything you are not certain about)."
        ),
        input_schema=schema(required={"path": "string", "reason": "string"}, optional={"severity": "string"}),
        annotations=REPORT_ONLY,
    )
    async def flag_for_review(args: dict) -> dict:
        severity = str(args.get("severity") or "warning")
        item = ctx.flag(str(args.get("path", "")), str(args.get("reason", ""))[:500], severity)
        return text_result(f"flagged {item.path} for manual review ({severity})")

    @tool(
        name="rollback_action",
        description="Undo a previously applied action from this audit by action id (refused if the page changed).",
        input_schema={"action_id": str, "reason": str},
        annotations=MUTATING,
    )
    async def rollback_action(args: dict) -> dict:
        try:
            action = ctx.actions.rollback(str(args.get("action_id", "")), str(args.get("reason", "")))
        except (KeyError, ValueError) as exc:
            return text_result(str(exc), is_error=True)
        ctx.reload()
        return text_result(f"rolled back {action.action_id} on {action.path}")

    return [set_frontmatter_field, add_frontmatter, regenerate_index, flag_for_review, rollback_action]
