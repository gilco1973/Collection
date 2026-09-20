# KnowledgeBase — handover

**Handover v5** · 2026-09-19 · branch `claude/vibrant-tesla-u7ccr3`, directory
`KnowledgeBase/` of the monorepo it was built in (self-contained; `git subtree split` makes
it a repository of its own) · package `KnowledgeBase-handover-v5.zip` built by
`scripts/handover.sh 5` (the manifest inside names the exact commit).

| Version | Date | Commit | What it contained |
| --- | --- | --- | --- |
| v1 | 2026-09-17 | `700b386f` | Knowledge base, librarian, API, console, four review rounds |
| v2 | 2026-09-18 | `ffec373f` | + animations, voice input, content translation (en/es/he), librarian chat |
| v3 | 2026-09-18 | `89c85141` | + security review package, enterprise sign-in, reader progress, personas, explain / elaborate / quiz me, nudges, operator-only audit UI |
| v4 | 2026-09-18 | `bf4edee3` | + production readiness: operator role from IdP groups, session revocation, reader-record retention, doctor, JSON logs, health/ready, daily chat ceiling, Kubernetes manifests + validator + runbook, hardened image; demo mode removed |
| v5 | 2026-09-19 | see `MANIFEST.txt` | + Phase 1 of the next-rounds plan: grounded retrieval (embedding index, `semantic_search`, hybrid search), the librarian evaluator (74-item golden set, thresholds, nightly run), insights (chat telemetry, k-anonymous aggregation, Insights tab); `design/SPEC-next-rounds.md` |

## What this is

A self-contained, organisation-neutral AI knowledge base for a bank (`docs/`, ten sections,
contract in `kb.config.yaml`), the **librarian agent** that keeps it healthy (deterministic
checks plus a Claude Agent SDK agent behind a permission gate, every change logged and
reversible), a FastAPI API and a React console, optional Atlassian mirroring, a security review
package with reviewer sign-off, enterprise sign-in with per-reader progress and chat actions,
everything an operator needs to run it in production, and — new in v5 — retrieval that finds a
page whose wording differs from the question, a measured librarian, and insights for owners.

## What changed since v4

The plan for the next rounds is `design/SPEC-next-rounds.md` (twelve workstreams in four phases).
This package delivers **Phase 1 — measure and retrieve**:

| Area | Delivered | Where |
| --- | --- | --- |
| Retrieval (§B) | Heading-bounded chunks, an `Embedder` protocol (`HashEmbedder` offline by default, `HttpEmbedder` for the bank's provider via `KB_EMBED_URL`/`KB_EMBED_MODEL`/`KB_EMBED_API_KEY`), a sqlite vector index on the state volume, the librarian's `semantic_search` read tool, `GET /api/search?mode=keyword|semantic|hybrid` (hybrid by default, reciprocal rank fusion, degrades to keyword without an index or over the 30/min per-client throttle), `kb-librarian index --embeddings` (re-embeds only changed chunks), a `doctor` check, a daily index CronJob | `kb_librarian/retrieval/`, `tools/read_tools.py`, `api/service.py`, `deploy/k8s/cronjob-index.yaml` |
| Evaluator (§E) | `evals/golden.yaml` (74 items: 55 en, 12 es, 7 he, 8 refusals), `kb-librarian eval` through the real chat path scoring citation precision/recall, keywords and refusal correctness against `kb.config.yaml` `evals:` thresholds (exit 0/1/2), JSON + Markdown reports, nightly `librarian-eval.yml` gated on the model secret, a governance page | `kb_librarian/evals/`, `cli_evals.py`, `docs/governance/librarian-evaluation.md` |
| Insights (§D) | One telemetry line per chat turn (`ts, mode, lang, persona, sources, refused, cost_usd, duration_ms`; never text), `kb-librarian insights` aggregating problem reports, views, quiz failures and unanswered questions per page under k-anonymity (`KB_INSIGHTS_K`, default 5), `GET /api/insights` + refresh (operator, same-origin), an Insights tab on the Audits page in 10 locales, `KB_CHAT_LOG_DAYS` pruning | `kb_librarian/insights/`, `chat/telemetry.py`, `web/src/components/InsightsPanel.tsx` |
| Leftovers (§F) | Submission packets for all 26 security modules generated (`kb-librarian security submit`); the rest recorded under "Known gaps" | — |

Every change carries tests seen failing first, a security sheet (three new modules: `retrieval`,
`evals`, `insights`), and passed the gates listed under "Verification". No page content changed
except the new governance page and the regenerated index.

## Architecture

| Layer | Where | Role |
| --- | --- | --- |
| Contract | `kb.config.yaml`, `kb_librarian/kbconfig.py` | Sections, owners, review windows, frontmatter, taxonomy, catalogs, i18n languages |
| Catalog / checks | `kb_librarian/catalog/`, `checks/` | Pages with frontmatter and links; structure, freshness, links, catalogs, sensitive content, `withholds`, `redact` |
| Agent / tools | `kb_librarian/agent/`, `tools/` | SDK runner, gate policy installed twice, hooks, in-process MCP read/write/Atlassian tools |
| Actions / reports | `kb_librarian/actions.py`, `reports.py` | Compare-and-swap writes, snapshots, rollback, redacted reports |
| Chat | `kb_librarian/chat/` | One read-only agent turn: ask / explain / elaborate / quiz; readable-only catalog; spend ledger; telemetry |
| Retrieval | `kb_librarian/retrieval/` | Chunks, embedders, sqlite vector index, retriever, hybrid ranking, throttle |
| Evaluation | `kb_librarian/evals/`, `evals/golden.yaml` | Golden items, scorer, runner, reports, thresholds |
| Insights | `kb_librarian/insights/` | k-anonymous aggregation of records, problems and telemetry |
| Identity | `kb_librarian/auth/`, `api/deps.py` | OIDC relying party, signed cookies, principal (key / group), epoch check per request |
| Profiles | `kb_librarian/profile/` | Per-reader JSON records, tombstones, retention |
| API | `kb_librarian/api/` | Router, admission, middleware (body cap, headers, CSP, request log), routes for pages / audits / chat / auth / profile, health |
| Settings | `kb_librarian/config.py` | Environment only, empty = unset, diagnostics without values |
| Security tooling | `kb_librarian/security/`, `security/` | Registry, versions, sign-off ledger, 24 sheets |
| Console | `web/` | React 18, TypeScript, Tailwind classes, TanStack Query, i18next (10 locales, RTL) |
| Deploy | `deploy/`, `.github/workflows/` | Image, compose, Kubernetes manifests, validator, runbook, CI, nightly / weekly / live-smoke jobs |

## How to run

Python 3.11 with Poetry, Node 22. Secrets come from the environment only; `.env.example`
lists every variable and no `.env` is ever read.

| Task | Command (from `KnowledgeBase/`) |
| --- | --- |
| Install | `poetry install` · `cd web && npm ci` |
| Backend gates | `poetry run ruff check . && poetry run ruff format --check . && poetry run pytest` |
| Console gates | `cd web && npm run lint && npm run i18n:check && npm test && npm run build` |
| Layout / neutrality gate | `scripts/verify-layout.sh` |
| Content contract | `poetry run kb-librarian check` |
| Manifests | `poetry run python scripts/validate_k8s.py deploy/k8s` |
| Host readiness | `poetry run kb-librarian doctor [--network] [--model]` |
| Search index | `poetry run kb-librarian index --embeddings` (offline hash embedder unless `KB_EMBED_URL` is set) |
| Evaluate the librarian | `poetry run kb-librarian eval [--items N] [--budget USD] [--lang xx]` (calls the model: costs money) |
| Insights | `poetry run kb-librarian insights [--json]` · `insights prune` |
| Serve API + console | `KB_API_KEY=<key> KB_ROOT=$PWD poetry run python deploy/serve.py` (port 8765) |
| Browser smoke | `BASE=http://127.0.0.1:8765 KEY=<key> node scripts/console-smoke.mjs` |
| Retention | `poetry run kb-librarian profiles purge --older-than-days N [--live]` · `profiles stats` |
| Security review | `poetry run kb-librarian security status` · `submit <module>` · `sign <module> …` · `verify` |
| Handover package | `scripts/handover.sh <version> [out-dir]` after updating this file |

Deploying: `deploy/RUNBOOK.md` (first deploy, secrets, upgrade, rollback, rotation, backup,
retention, health, logs and alerts). Sign-in needs `KB_OIDC_ISSUER`, `KB_OIDC_CLIENT_ID`,
`KB_OIDC_REDIRECT_URI` (https) and `KB_SESSION_SECRET` (32+ characters); operators come from
`KB_OIDC_OPERATOR_GROUPS` or the break-glass `KB_API_KEY`. Live audits still need
`KB_ALLOW_LIVE=true`; Atlassian writes additionally `KB_ATLASSIAN_ALLOW_WRITE=true`.

## Safety model (what a reviewer should know)

- **Dry run by default**, enforced at the server, the gate, the action log and the Atlassian
  client; denials recorded; every live change snapshotted and rollback-able.
- **Withholding**: any critical/error sensitive hit keeps a page from readers, search, facets,
  the raw catalog endpoint, the chat's catalog (also across tool reloads) and the profile.
- **Authorisation**: the session identifies a reader; the operator role comes from an IdP group
  decided at sign-in (re-evaluated at the next sign-in) or from the shared key; cookie-authenticated
  mutations, operator ones included, refuse cross-site requests.
- **Revocation fails closed**: the epoch check runs on every cookie request; "delete my data"
  keeps the epoch; an unreadable record becomes a tombstone with a fresh epoch; retention keeps
  epochs until every older cookie has expired.
- **Attribution without exposure**: reports (viewer-readable, exportable) carry `key` or a
  pseudonym keyed with the session secret; the subject appears only in the server log.
- **Model text is data**: tool results are enveloped, chat answers and quiz text render as
  plain text, links only come from the pages actually read, selections are bounded.
- **Cost**: per-turn ceilings, a per-client throttle and a per-day ledger for chat; audit budgets
  reserved at admission.
- **Logs and diagnostics never carry a value**: request ids are validated, paths are cleaned of
  control characters, `doctor` reports presence and length class only, settings errors name the
  variable only.
- **Deployment**: non-root, read-only root filesystem, no capabilities, seccomp, no service-account
  token, ClusterIP + NetworkPolicy, both gates `"false"` in every manifest, empty Secret template;
  a job names the one secret key it needs, never the whole Secret (validator-enforced).
- **Retrieval never widens what a reader may see**: the index holds every page (Internal tier, on
  the state volume) but every query joins on the caller's readable paths inside the database;
  excerpts come only from allowed chunks; page text leaves the host only through the configured
  embedder (the offline default sends nothing).
- **Aggregates, not people**: a telemetry line holds paths and flags, never a message; insights
  withhold every reader-derived number below `k` distinct readers; eval reports contain authored
  questions and model answers only.

## Review history

| Round | Scope | Outcome |
| --- | --- | --- |
| 1–4 (v1) | Whole product, harness process | All Critical/Important fixed; see `.harness/runs/` |
| Security package, sign-in, integration (v3) | `f30d08c5..72543988` | 1 Critical + 25 Important fixed across the rounds; workflow panel of 80 agents |
| Phase 1 (v5) | `c0076af4..45b543be` | Panel workflow (6 lenses → verifiers), product reviewer and auditor all cut off by the weekly subagent limit before any finding; each loop ran the `code-review` skill on its own branch (retrieval fixed 9 of its 10 findings before hand-back), and the integrator reviewed the withholding, k-anonymity, telemetry, throttle, budget-stop and manifest surfaces by hand: 2 findings, both fixed in `45b543be` (index CronJob mounted the whole Secret; unbounded `lang` reaching telemetry). A full panel run is the first item under "Known gaps" |
| Production (v4) | `89c85141..3e978529` | Panel workflow: 2 of 6 lenses (security, backend) completed before the weekly subagent limit; their 16 findings were triaged by hand — 3 Critical/Important clusters (empty environment values crashed the process; revocation lost through purge or an unreadable record; unkeyed pseudonym) and every minor fixed in `6ad10cca`. Product reviewer: Works / Usable / Regressions pass; its four findings (settings tracebacks, doctor vs the CLI's credential store, README pointers, `KB_ROOT`) fixed in the same commit. The adversarial verifiers, the other four lenses and the harness auditor did not run — see "Known gaps" |

Verification at v5 head: backend 414 tests / 97.1% coverage, console 137 tests / 99.4%, lint,
typecheck, 324 keys × 10 locales, layout, contract check, manifest validator, browser smoke 33/33
(incl. hybrid search mode, health/ready, request ids), and criteria drives: the index built (247
chunks over 53 pages) and rebuilt with 0 re-embeddings, `doctor` reports it, `eval --items 2
--budget 0.1` ran two golden items against the real model ($0.09; precision 0.75 reported as a
threshold miss, exit 1 — the first full nightly run sets the baseline), insights generated and
served after refresh. Raw logs with exit codes in the run's evidence directory. No security module
is signed yet; the 26 submission packets are ready.

## Known gaps and next steps

1. **Review completion**: run the six-lens panel with adversarial verification and the harness
   auditor over `c0076af4..45b543be` once subagent capacity returns; only a hand review ran.
2. **Baseline the evaluator**: the first `librarian-eval.yml` run (74 items, ≈ $3–4) sets the
   numbers; decide the refusal rule for an honest "no page covers this" given after reading pages
   (today it counts as cited, not refused).
3. **Embedding provider**: the offline hash embedder is token overlap only; choose the on-prem
   or contracted endpoint (`KB_EMBED_URL`) — the bank's decision (spec §5.1). Localised pages are
   fused by keyword only until per-language chunks are added.
4. **Sign-offs**: hand the 26 packets to the security team; wire `security verify` into the
   release branch once the first sign-offs exist; add a CODEOWNERS rule for `security/`.
5. **Cluster parameters**: ingress namespace label, `FORWARDED_ALLOW_IPS`, egress 443 narrowing;
   no cluster or Docker run happened in the build sandbox (manifests validated statically).
6. **Retire the shared key** once every operator signs in through a group; **subject in the
   server log** at audit start and **translation notice** remain decisions for privacy and product.
7. **Phase 2 (propose and approve)** is next per `design/SPEC-next-rounds.md`: the proposal
   action shape, the scout, the steward and the authoring copilot.

## Key files

`README.md` · `CLAUDE.md` · `deploy/RUNBOOK.md` · `security/README.md` · `docs/integrations/console.md` ·
`docs/integrations/platform.md` · `kb.config.yaml` · `kb_librarian/agent/gate.py` · `kb_librarian/api/deps.py` ·
`kb_librarian/auth/principal.py` · `kb_librarian/profile/store.py` · `kb_librarian/api/observability.py` ·
`kb_librarian/cli_doctor.py` · `kb_librarian/retrieval/index.py` · `kb_librarian/evals/runner.py` ·
`kb_librarian/insights/collect.py` · `evals/golden.yaml` · `design/SPEC-next-rounds.md` ·
`deploy/k8s/deployment.yaml` · `scripts/validate_k8s.py` · `scripts/handover.sh`
