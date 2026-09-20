# KnowledgeBase

The unified organisational AI knowledge base: everything a new joiner needs to read,
watch, learn and follow to build AI on the paved roads, plus the **librarian agent**
that keeps it accurate, complete, current, navigable and safe.

Content is organisation-neutral and written for a regulated financial institution:
model risk management, data classification, prompt-injection defence, human ownership
of outcomes and audit trails are first-class, not appendices.

## What is here

| Path | Contents |
| --- | --- |
| `docs/onboarding/` | Day one, first week, 30/60/90, reading list, checklist |
| `docs/paved-roads/` | LLM gateway, assistant, RAG, agent with tools, evaluation pipeline, model lifecycle |
| `docs/best-practices/` | Prompting, agent design, security, data classification, responsible AI, cost, observability |
| `docs/skills/` | Agent skills catalog (`SKILL.md` folders) and template |
| `docs/videos/` | Catalog of recorded sessions (`catalog.yaml`) |
| `docs/tutorials/` | Five ordered hands-on tutorials |
| `docs/wiki/` | Glossary, FAQ, decision records |
| `docs/integrations/` | Atlassian (Confluence + Jira), the platform mount, the console for readers |
| `docs/resources/` | Curated external references (`catalog.yaml`) |
| `docs/governance/` | Content standards, review process, taxonomy, model risk, the librarian |
| `kb.config.yaml` | The contract the librarian enforces: sections, owners, review windows, frontmatter, taxonomy |
| `kb_librarian/` | The librarian: deterministic checks, Claude Agent SDK agent, Atlassian clients, CLI, API |
| `web/` | The console: React + Vite + TypeScript, Tailwind classes, i18next (10 languages, RTL) |
| `docs/i18n/<lang>/` | Machine-translated copies of `docs/`, written by `kb-librarian translate sync` |
| `deploy/` | Dockerfile, compose file and single-process server for the AI Platform |
| `tests/` | Test suite (coverage gate 87%) |
| `design/UI-DESIGN.md` | The console's UI/UX specification |
| `.librarian/` | Runtime state (reports, page snapshots, cancel markers); never committed |

Start reading at `docs/index.md`.

## The librarian in one minute

```bash
poetry install
poetry run kb-librarian check                 # deterministic checks; exit 1 on errors (CI gate; nothing persisted)
poetry run kb-librarian audit --offline       # same checks, written as a report
poetry run kb-librarian audit                 # Claude Agent SDK audit, DRY RUN (the default)
poetry run kb-librarian reports list
poetry run kb-librarian cancel <audit id>     # deny the running audit's next tool call
poetry run kb-librarian rollback <audit id> <action id> --reason "..." [--force]
```

A live audit that may edit pages needs `KB_ALLOW_LIVE=true` in the environment *and*
`--live`; anything else is forced to dry run. Live Atlassian writes additionally need
`KB_ATLASSIAN_ALLOW_WRITE=true`. See `docs/governance/librarian-agent.md` for the full
safety model and `docs/integrations/atlassian.md` for the Atlassian setup.

## Content translation

`kb-librarian translate sync` is the nightly job: it hashes every page's title and body,
skips anything already translated at its current hash (or sensitive, or missing
frontmatter), and machine-translates the rest into the languages `kb.config.yaml`'s
`i18n.languages` lists (Claude Agent SDK, one page at a time — no tools, no network
beyond the model call). Output lands under `docs/i18n/<lang>/...`, mirroring `docs/`
path-for-path; English stays the single source of truth (owner, status, tags, audience
and `reviewed` are copied unchanged, never invented). Writes go through the same
`ActionLog` audits use, so a bad machine translation is `kb-librarian rollback` like any
other action, and the run is a normal report (`kb-librarian reports list`).

```bash
poetry run kb-librarian translate sync                 # DRY RUN unless KB_ALLOW_LIVE=true and --live
poetry run kb-librarian translate sync --live           # write docs/i18n/<lang>/...
poetry run kb-librarian translate sync --languages es   # override kb.config.yaml for one run
```

This process has no built-in scheduler; point cron (or a systemd timer, or a CI
scheduled workflow) at the live form nightly, e.g.:

```cron
0 3 * * * cd /path/to/KnowledgeBase && KB_ALLOW_LIVE=true poetry run kb-librarian translate sync --live >> /var/log/kb-translate.log 2>&1
```

The console's page view offers a content-language picker (English/Spanish/Hebrew) that
requests a page with `?lang=es`; a page not yet translated falls back to English.

The container image is dry-run only unless `docs/` is bind-mounted (the compose file does)
and something commits the result to git; `.librarian/` (reports, snapshots, cancel markers,
problem reports) is runtime state and is never committed.

Authentication for the agent is inherited from the environment (`ANTHROPIC_API_KEY` or
`CLAUDE_CODE_OAUTH_TOKEN`), supplied by your secret manager. `.env.example` lists every
variable; never commit a `.env`.

## Console and API

```bash
poetry run kb-librarian-api                   # JSON API on http://127.0.0.1:8765/api (docs at /api/docs)
cd web && npm ci && npm run dev               # console on http://localhost:5173, proxies /api
cd web && npm run lint && npm run i18n:check && npm test && npm run build
docker compose -f deploy/compose.yaml up --build   # API + console in one container
node scripts/console-smoke.mjs                # browser smoke test against a running server (see file header)
```

Operating it: `kb-librarian doctor [--network] [--model]` checks a host before and after a deploy
(exit 0/1/2; a rejected setting is one `FAIL settings — KB_<VAR>` line), `GET /api/health` and
`/api/health/ready` are the probes, every request logs one JSON line with a `request_id`,
`KB_CHAT_DAILY_BUDGET_USD` caps the chat's spend per day, and `kb-librarian profiles purge|stats`
applies `KB_PROFILE_RETENTION_DAYS` to reader records. `deploy/k8s/` holds the Kubernetes
manifests (validated by `scripts/validate_k8s.py` in CI) and `deploy/RUNBOOK.md` the operator's
guide: first deploy, secrets, upgrade, rollback, rotation, backup, retention, alerts.

Readers browse and search pages and report problems; operators (an IdP group, or bearer `KB_API_KEY`)
start dry-run or live audits, watch progress, work the review queue, read the tool trail
and roll actions back. See `docs/integrations/platform.md` for mounting the API inside the
AI Platform and `design/UI-DESIGN.md` for the screens.

Readers also get, described in `docs/integrations/console.md`: sign-in with the
organisation's identity provider (OpenID Connect, `kb_librarian/auth/`), reading progress
and personas kept per reader (`kb_librarian/profile/`), and the "Ask the librarian" chat
with its Explain / Elaborate / Quiz me actions on selected text (`kb_librarian/chat/`,
read-only tools, its own ceilings `KB_CHAT_MAX_TURNS` / `KB_CHAT_MAX_BUDGET_USD`), and
browser-side suggestions computed from that progress (nothing tracked server-side).
`.env.example` lists every variable these need.

## Architecture

```
kb.config.yaml ──► kbconfig ──► catalog (frontmatter + links) ──► checks ──► findings
                                                                      │
                     ┌────────────────────────────────────────────────┘
                     ▼
   run_offline_audit ──► AuditReport ──► .librarian/reports/<id>.{json,md}
   run_agent_audit   ──► Claude Agent SDK query()
                          ├─ in-process MCP server: read tools, write tools, Atlassian tools
                          ├─ one GatePolicy installed twice: can_use_tool + PreToolUse hook
                          │    (unknown tool → deny; mutating in dry-run → deny; denials recorded)
                          ├─ hooks: cancel check, PostToolUse/PostToolUseFailure audit trail
                          └─ options: tools=[] (no built-ins), nothing pre-approved, max_turns, max_budget_usd
```

## Security review and sign-off

`security/` is the review package for the AI security team: `registry.yaml` names every
reviewable module (backend packages, console components, deployment, the tooling itself) and
`security/modules/<id>.md` is its review sheet — purpose, entry points, trust boundaries, data,
secrets, external calls, mutations, controls, residual risks, checklist and the sign-off table.

```bash
poetry run kb-librarian security status          # every module: content version and sign-off state
poetry run kb-librarian security submit api-core # submission packet: sheet + per-file SHA-256 manifest
poetry run kb-librarian security sign api-core --reviewer "…" --signature "…" --decision approved
poetry run kb-librarian security verify          # exit 1 when any module is unsigned or changed since signing
```

A module's version is a hash of its files, so a sign-off is bound to exactly the code that was
reviewed and `status` reports `changed` the moment it drifts. Sign-offs live in
`security/signoffs/<id>.json` and as a row in the sheet, both committed. See `security/README.md`.

## Development

```bash
poetry run ruff check . && poetry run ruff format --check .
poetry run pytest                             # enforces --cov-fail-under=87
scripts/verify-layout.sh                      # required sections, files, size limits
```

Rules for contributors are in `CLAUDE.md` (they apply to people and agents alike).

## Splitting into its own repository

This directory is self-contained. To publish it as a standalone repository:

```bash
git subtree split --prefix=KnowledgeBase -b knowledgebase-standalone
```

`.github/workflows/ci.yml` inside this directory is the standalone CI; the monorepo
uses `knowledgebase-ci.yml` at the monorepo root.
