---
title: The librarian agent
owner: ai-platform-engineering
status: active
reviewed: 2026-09-15
tags: [governance, agents, security]
audience: [everyone]
---
# The librarian agent

The librarian is an autonomous agent, built on the Claude Agent SDK, that audits this
knowledge base and keeps it healthy. It is also the reference implementation of the
[agent with tools](../paved-roads/agent-with-tools.md) paved road: read its code to see
the rules applied.

## What it checks (without a model)

Deterministic checks run first, every time, and alone in CI:

| Check | Finds |
| --- | --- |
| structure | Sections without a landing page, a missing index, orphan pages |
| frontmatter | Missing blocks or fields, bad status or audience, tags outside the taxonomy, bad dates |
| freshness | Pages past their section's review window |
| links | Broken internal links; external hosts outside the trusted list |
| sensitive | Credentials, keys, tokens, IBANs, card numbers, secret assignments, emails and IPs (pages and YAML catalogs, frontmatter included) |
| catalogs | `videos/catalog.yaml` and `resources/catalog.yaml`: required fields, dates, URL hosts |

## What it may do (with a model)

| Tool | Mutating | Dry-run behaviour |
| --- | --- | --- |
| list_documents, get_document, search_documents, run_checks, get_contract | No | Allowed |
| add_frontmatter, set_frontmatter_field (contract fields only, never `reviewed`), regenerate_index, rollback_action | Yes | Denied by the gate |
| flag_for_review | No (report only) | Allowed |
| confluence_search, confluence_get_page | No | Allowed when configured |
| confluence_publish_page, jira_create_issue | Yes | Denied by the gate |

It never bumps a page's `reviewed` date, never rewrites prose, never deletes a page,
and never quotes a sensitive value. Stale content goes to the owner via `flag_for_review`.

**Withholding rule.** A page or catalog file whose current text contains a `critical` **or**
`error` sensitive hit (keys, tokens, private keys, connection strings, secret assignments, IBANs,
card numbers) is withheld from readers: the API serves no body, no snippet and redacted metadata,
and the console shows the "withheld pending review" notice. Two triggers withhold: the page's current
text (cleared the moment the text is clean) and a sensitive finding in the latest completed audit
(cleared by the next completed audit, so run one after a clean-up instead of waiting for the nightly). The rule
is `kb_librarian.checks.sensitive.withholds` and is the same for pages, catalogs and search.
External-link probing resolves each host and refuses non-public, NAT64, 6to4 and multicast
addresses; it does not pin the connection to the vetted address, so run network audits from an
egress-restricted runner if DNS rebinding is in your threat model.

## Safety properties

- **Dry run by default.** Live runs need `KB_ALLOW_LIVE=true` on the server; a caller
  asking for live without it is forced to dry run and told so.
- **Gate in code, twice.** One policy (unknown tool → deny; mutating tool in dry run →
  deny; mutating call without a reason → deny) is installed as the SDK's `can_use_tool`
  callback *and* as a `PreToolUse` hook. The hook exists because the SDK auto-approves
  any tool named in `allowed_tools` before the callback runs, so the librarian never
  pre-approves anything and the hook catches every call regardless.
- **No built-in tools.** The agent runs with `tools=[]`, which removes every built-in
  (file, shell, web, tool search); a deny-list names the important ones as a second
  layer. The knowledge base is edited only through the audited kb tools.
- **Budgets.** `max_turns` and `max_budget_usd` per run. The SDK enforces the spend cap
  between turns, so one expensive turn can overshoot it; size the cap with that margin.
- **Audit trail.** Every tool call, every denied call, every action (with SHA-256 of the
  page before and after), every manual review item, in `.librarian/reports/<audit id>.json`
  and `.md`. Free text in the report is passed through the sensitive-content redactor
  before it is written; page contents live only in `.librarian/snapshots/`, which is never
  uploaded anywhere.
- **Rollback.** Any applied action can be undone by id. Rollback refuses when the page has
  changed since the action unless `--force` is given, and records that it was forced.
- **Cancel.** `kb-librarian cancel <audit id>` writes a marker the running audit checks
  before every tool call; the next call is denied and the agent is told to summarise.

## Running it

```bash
kb-librarian check                          # CI gate: deterministic checks, exit 1 on errors
kb-librarian audit --offline                # deterministic report, no model
kb-librarian audit                          # agent audit, dry run
KB_ALLOW_LIVE=true kb-librarian audit --live --capabilities frontmatter,structure
kb-librarian reports list | show <id>
kb-librarian rollback <audit id> <action id> --reason "..."
```

Scheduled: a nightly dry-run audit (`librarian-nightly.yml`) publishes its markdown
report as a build artifact. A weekly live audit limited to `frontmatter,structure`
(`librarian-weekly-live.yml`) exists but only runs when the repository variable
`KB_WEEKLY_LIVE` is `true`, with a named operator on call; it uses the write-capable
Atlassian service account, the nightly uses the read-only one.
