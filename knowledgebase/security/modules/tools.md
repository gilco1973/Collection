# Security review sheet: In-process MCP tool server

| | |
| --- | --- |
| Module id | `tools` |
| Kind | backend |
| Code | `kb_librarian/tools/` (`server.py`, `context.py`, `read_tools.py`, `write_tools.py`, `atlassian_tools.py`) |
| Tests | `tests/test_actions_tools.py`, `tests/test_agent_layer.py`, `tests/test_atlassian.py`, `tests/test_retrieval_chat.py` |
| Depends on | claude-agent-sdk, mcp, `retrieval` |

## Purpose

The **entire** tool surface the librarian model can call: an in-process MCP server named `kb`
with read tools (`list_documents`, `get_document`, `search_documents`, `run_checks`,
`get_contract`, and `semantic_search` when `ToolContext.retriever` is set), write tools (`set_frontmatter_field`, `add_frontmatter`, `regenerate_index`,
`rollback_action`; `flag_for_review` is report-only) and, when enabled, Atlassian tools
(`confluence_search`, `confluence_get_page`, `confluence_publish_page`, `jira_create_issue`).

## Entry points

`build_kb_tools(ctx, extra)`, `build_kb_server(tools)`, `build_read_tools`, `build_write_tools`,
`build_atlassian_tools`, `mutating_names(tools)`, `qualified/unqualify`.

## Trust boundaries

Tool **inputs come from the model** and are untrusted. Tool **outputs return page content to
the model** and are wrapped by `data_result()` in a labelled envelope (`DATA_PREAMBLE` +
`<kb-data>`) so the prompt states that it is data, not instruction.

## Data handled

Page frontmatter/body (bodies capped at `MAX_BODY_CHARS` = 20 000), findings, the contract,
Confluence page bodies and search hits.

## Secrets

None in this module; Atlassian credentials live in the client passed in.

## External calls

Atlassian tools call Confluence/Jira through the gated client. Everything else is local.

## Mutations

Only through `ctx.actions` (the action log) or `ctx.record_external_action`. Every mutating
tool is annotated `readOnlyHint=False`; `mutating_names()` derives the mutating set from
annotations and **raises if a tool has none**, and `MUTATING_TOOLS` documents the same set (a
test keeps them equal). Mutating tools take a `reason` and are inert in dry-run (defence in
depth behind the gate: `ActionLog` also refuses to write).

## Controls in place

- Write tools validate fields against the contract (`validate_field`): only required
  frontmatter fields + `review_every_days`; enumerations enforced. `set_frontmatter_field`
  refuses `reviewed` (owner-only). `add_frontmatter` — a page with *no* frontmatter — accepts a
  `reviewed` value because the contract requires the field; that is the one place the librarian
  writes a review date, and the page's owner should confirm it (see residual risks).
- `run_checks` reloads the catalog from disk; `ToolContext.reload` re-applies the caller's
  `view`, so a reload can never widen what the model sees.
- `semantic_search(query, limit=8)` (read-only, not in `MUTATING_TOOLS`) is registered only when
  `ToolContext.retriever` is set (an embedding index exists). Every call passes the paths of
  `ctx.catalog` — the caller's view, withheld pages already removed — as the index query's
  `allowed_paths`, so a hit is never a page the model could not `get_document`; `limit` is clamped to
  1–20; rows are `{path, heading, excerpt, score}` (score rounded to 3 places) in the data envelope;
  an `EmbedError` becomes an error result, never an exception.
- CAS: writes carry `expected_text=doc.raw`; a page changed since read is refused.
- `flag_for_review` truncates reasons to 500 chars; Jira summary/description capped
  (200/2000); CQL input has quotes and backslashes stripped and is capped at 200 chars.
- Tool names are namespaced (`mcp__kb__*`); `strict_mcp_config` keeps other servers out.

## Residual risks and reviewer attention points

- The data envelope is a mitigation, not a guarantee, against prompt injection from pages; the
  gate, dry-run default and budgets bound the blast radius.
- `run_checks` with `offline=False` performs outbound HTTP link checks initiated by the model
  (only when the audit was started with network enabled by an operator).
- `set_frontmatter_field` parses JSON for list/object values; a malformed value falls back to
  the raw string and is then rejected by validation for enumerated fields.
- `add_frontmatter` can set an initial `reviewed` date on a page that had none (CLAUDE.md:
  "only a page owner bumps `reviewed`"). Live runs are opt-in and land as a PR, so the owner
  reviews it; a stricter policy would require `reviewed` to be flagged for review instead.

## Reviewer checklist

- [ ] Every tool has annotations; `MUTATING_TOOLS` equals the annotation-derived set.
- [ ] No tool reads or writes outside the docs root or `.librarian/`.
- [ ] Any new tool that changes state records an action and requires `reason`.

## Sign-off

Submit with `kb-librarian security submit tools`; the reviewer records the decision with
`kb-librarian security sign tools …`, which appends a row here and to `security/signoffs/tools.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
