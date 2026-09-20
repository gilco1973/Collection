# Security review sheet: Agent runtime

| | |
| --- | --- |
| Module id | `agent` |
| Kind | backend |
| Code | `kb_librarian/agent/` (`gate.py`, `hooks.py`, `options.py`, `prompts.py`, `runner.py`, `task_manager.py`) |
| Tests | `tests/test_agent_layer.py`, `tests/test_runner.py`, `tests/fake_query.py` (runs the real gate/hooks/tools against a fake model stream) |
| Depends on | claude-agent-sdk |

## Purpose

Runs one librarian audit with the Claude Agent SDK: deterministic checks first, then the
model works the findings using only the `kb` MCP tools. **`gate.py` is the only place tool
execution is decided.**

## Entry points

`run_offline_checks`, `run_offline_audit`, `run_agent_audit(settings, root, dry_run=, capabilities=,
offline=, max_turns=, max_budget_usd=, tool_factories=, query_fn=, manager=, reason=, requested_by=)`,
`AuditTaskManager.cancel/is_cancelled`.

## Trust boundaries

- The model is an untrusted actor with a bounded tool surface. Everything it can do goes
  through `GatePolicy` — installed twice: as `can_use_tool` and as a `PreToolUse` hook (no
  allow rule can shadow the hook). Denials are written to the audit trail.
- Operators choose mode/capabilities/budget, but the server-side `KB_ALLOW_LIVE` gate wins.
- Cancellation is reachable from another process via a marker file under `.librarian/cancel/`.

## Data handled

Findings digest (first 15) and the contract go into the prompt; page content flows through
tools. Read-tool responses are recorded in the trail as **length only** (never text), so a
viewer cannot read a withheld page through the trail; mutating tool responses are truncated
to 300 chars. Tool **inputs** the model chose (`reason`, `query`, Jira text) are recorded
verbatim and pattern-redacted on save — see `api-audits.md` residual risks: model-authored
prose is not guaranteed clean. Cost, turns and the model's summary are stored on the report.

## Secrets

None read here; the SDK reads `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` from the environment.

## External calls

The model API (via the SDK). No other network access: `tools=[]` removes every built-in Claude
Code tool and `DISALLOWED_BUILTINS` denies them again by name (Bash, Write, Edit, Read, Glob,
Grep, WebFetch, WebSearch, Task/Agent, Skill, …). `setting_sources=[]` ignores host settings;
`strict_mcp_config=True` prevents extra MCP servers.

## Mutations

None directly. The gate denies any mutating tool in dry-run and any mutating call without a
non-empty `reason`; unknown tools are denied; **any exception while evaluating a call is a deny**.

## Controls in place

- `allowed_tools=[]` so nothing is pre-approved before `can_use_tool`; `permission_mode="default"`.
- `max_turns` and `max_budget_usd` from settings/operator, clamped by the API's admission.
- The report is saved before the run (visible/cancellable) and in `finally` (never lost);
  failures/cancellations are recorded as such.
- Deterministic phase runs off the event loop (`to_thread`) so a long scan cannot stall the API.

## Residual risks and reviewer attention points

- SDK budget enforcement happens between turns; a single turn can overshoot.
- The SDK's own permission-denial reporting is merged into the trail defensively; if the SDK
  changes its payload shape, denials are still recorded by the hook.
- Prompt injection from page content could steer which *allowed* tools the model calls; the
  allowed set in dry-run is read-only, and live runs are opt-in and reviewed via reports/PRs.

## Reviewer checklist

- [ ] `GatePolicy._deny_reason` order: unknown → dry-run mutating → missing reason; fail-closed wrapper intact.
- [ ] `build_options`: `tools=[]`, `allowed_tools=[]`, `disallowed_tools` includes the full list, `setting_sources=[]`, `strict_mcp_config=True`.
- [ ] `record_tool_call` stores length only for read tools.

## Sign-off

Submit with `kb-librarian security submit agent`; the reviewer records the decision with
`kb-librarian security sign agent …`, which appends a row here and to `security/signoffs/agent.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
