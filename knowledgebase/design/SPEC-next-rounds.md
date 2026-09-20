# KnowledgeBase — next rounds: specification and plan

**Status:** proposal · 2026-09-18 · written against commit `bf4edee3` (handover v4).
**Scope:** the six gaps named in the v4 assessment and the eight agentic enhancements, as one
programme of four phases. Every design below reuses the controls that exist today: the
permission gate (`agent/gate.py`), `MUTATING_TOOLS`, the dry-run gate `KB_ALLOW_LIVE`, the
action log with snapshots and rollback, withholding, the security registry and sheets, the
10-locale rule, the 200-line rule, and secrets from the environment only.

Numbers and file names in this document come from the tree at that commit, not from memory.

---

## 0. Correction to the assessment

The assessment said the wiki has "no glossary or decision log" and the skills section has "one
template". Both are wrong: `docs/wiki/` holds `glossary.md` (53 lines), `faq.md` (53) and two
ADRs; `docs/skills/` holds three skills (`code-review`, `incident-summary`, `policy-qa`, 40–47
lines each) plus the template. What is true: 52 pages across ten sections average ~35 lines,
the videos catalog is entirely `placeholder`, the tutorials stop at five short pages, and no
section defines a **path** a persona follows to a **checkpoint**. Depth and paths are the gap.

## 1. What exists that the programme builds on

| Building block | Where | Used by |
| --- | --- | --- |
| Read tools `list_documents`, `get_document`, `search_documents`, `get_contract`, `run_checks` | `kb_librarian/tools/read_tools.py` | B, E, G, I |
| Mutating tools set and the gate (`set_frontmatter_field`, `add_frontmatter`, `regenerate_index`, `rollback_action`, `confluence_publish_page`, …) | `tools/server.py::MUTATING_TOOLS`, `agent/gate.py` | C, G, I, K |
| Capabilities and prompts (`structure`, `frontmatter`, `freshness`, `links`, `sensitive`, `atlassian`) | `agent/prompts.py::CAPABILITY_PROMPTS` | C, G, H, K |
| Action log, snapshots, rollback, reports | `actions.py`, `reports.py`, `.librarian/reports/` | C, G, I |
| Chat runner (one read-only turn, modes ask/explain/elaborate/quiz, readable-only catalog view) | `chat/runner.py`, `chat/prompts.py` | B, E, H, I |
| Sensitive-content scanner and withholding | `checks/sensitive.py`, `service.readable_page`, `withheld_paths` | C, K, L |
| Keyword search (substring over title and body) | `catalog/catalog.py::search`, `api/service.py::search` | B replaces |
| Reader records (views, persona, quizzes, epoch) | `profile/models.py`, `profile/store.py` | D, H |
| Problem reports (`POST /api/pages/{path}/reports` → `.librarian/problems/problem-*.json`, cap 500) | `api/routes_pages.py` | D, G |
| Atlassian clients (Confluence `search`, `get`, `publish`; Jira `search`, `create_issue`) and agent tools | `atlassian/`, `tools/atlassian_tools.py` | C, G |
| Content contract (`sections`, `audience_values`: new-hire, engineer, data-scientist, product, risk, leadership, everyone; `catalogs`; `i18n.languages`: es, he) | `kb.config.yaml` | A, H |
| Jobs: nightly dry-run audit, weekly live audit (PR), live smoke; CLI `check / audit / index / translate / profiles / doctor / security` | `.github/workflows/`, `cli.py` | B, C, E, G, J |
| Console: reader pages, selection toolbar, chat widget, quiz card, nudges, operator audits/review queue | `web/src/` | H, I |

## 2. Principles every workstream is bound by

1. **Nothing lands in `docs/` without the live gate and a human.** Agents propose; the action log
   records; an operator (or the weekly PR job) applies. New write paths are new entries in
   `MUTATING_TOOLS`, take a `reason`, and do nothing to disk in dry-run.
2. **Withheld stays withheld** in every new surface: embeddings, insights, evals, guard, paths.
3. **No reader is identifiable in an aggregate.** Insights, path statistics and eval logs carry
   paths, counts and rates; a bucket below `k = 5` readers is not reported.
4. **No secret, no message text in logs or reports** (the v4 rules extend to chat logs and transcripts).
5. **Every new file has a module and sheet** in `security/registry.yaml`; every user-visible
   string ships in 10 locales; every file stays under 200 lines; every behaviour has a test seen
   failing first; the panel review runs before "done".
6. **Cost is bounded per turn, per client and per day** for every new agent path, and the nightly
   jobs carry their own ceilings.
7. **Provider-neutral where the bank has a choice** (embeddings, speech-to-text): a small protocol
   with an HTTP implementation and a local implementation, chosen by environment.

---

## 3. Workstreams

Each workstream: goal · design · data · gates · tests and success criteria · effort (in
agent-loop days, one loop = one worktree) · depends on.

### A. Content depth and persona paths

**Goal.** Every persona in `audience_values` has a path: an ordered list of pages ending in a
checkpoint, and every page on it teaches rather than lists.

**Design.**
- `kb.config.yaml` gains `paths:` — `{persona, title, steps: [{path, kind: read|do|watch}],
  checkpoint: {quiz_page, pass_score}}` for engineer, data-scientist, product, risk, new-hire
  (leadership gets a two-page briefing path). `kbconfig.py` validates that every step exists,
  is not withheld, and carries the persona in its `audience`.
- A `paths` check (`checks/paths.py`): every path's pages exist and are `active`; every persona
  has a path; a checkpoint quiz page exists. `kb-librarian check` fails on a broken path.
- Content work (the bulk): tutorials 01–05 rewritten to ~120-line lessons with exercises;
  `docs/skills/` grows to eight skills (prompt review, data classification, incident summary,
  model card, red-team checklist, eval design, RAG grounding, vendor review); the videos catalog
  gets scripts (`docs/videos/scripts/<id>.md`) so a placeholder becomes recordable; the wiki gains
  ten ADRs from the bank's actual decisions (owners supply), a "who to ask" page and a
  per-persona FAQ; governance gains the model-risk lifecycle walk-through with the forms.
- Checkpoint pages are quiz pages: frontmatter `checkpoint: true`, body lists the questions the
  agent's `quiz` mode must draw from (so the quiz is grounded, not improvised).

**Data.** Pages only. Path progress is computed from the existing `viewed` and `quizzes`.

**Gates.** Content passes `kb-librarian check` (sensitive scanner, links, frontmatter) as today.

**Tests / criteria.** `paths` check fails on a fixture with a missing step (seen failing first);
`kb-librarian check` exit 0 on the tree; every persona has ≥ 1 path; `docs/index.md`
regenerated; a reader on the engineer persona sees "Your path: 3 of 9" on Home (H consumes it).

**Effort.** 1 loop-day for config/check; 4–6 loop-days of content, best split per section with
owners reviewing (content is the one thing an agent must not invent: it drafts, owners approve).

**Depends on.** Nothing. Feeds H.

### B. Grounded retrieval (embedding index + `semantic_search`)

**Goal.** A question phrased unlike the page still finds it — for readers (`/api/search`) and
for the librarian's chat grounding.

**Design.**
- `kb_librarian/retrieval/` (new module): `chunks.py` splits a page into heading-bounded chunks
  (≤ ~800 tokens, id `path#slug`, content hash); `embedder.py` defines `Embedder` (protocol:
  `embed(texts) -> list[list[float]]`, `dim`, `model_id`) with `HttpEmbedder` (any
  OpenAI-compatible or Voyage-style endpoint via `httpx`; `KB_EMBED_URL`, `KB_EMBED_MODEL`,
  `KB_EMBED_API_KEY`) and `LocalEmbedder` (optional extra `kb-librarian[local-embeddings]`
  wrapping a sentence-transformers model, for banks that keep text on-prem); `index.py` stores
  vectors in `.librarian/index/embeddings.sqlite` (chunk id, path, hash, model, float32 blob) and
  answers `query(vector, limit, allowed_paths)` with cosine similarity in pure Python (a KB of a
  few thousand chunks needs no vector database; the interface allows one later).
- Build: `kb-librarian index --embeddings` (idempotent: only chunks whose hash changed are
  re-embedded); the nightly job runs it before the audit; `AppState` rebuilds lazily when the
  catalog stamp changes and the index is stale.
- Read tool `semantic_search(query, limit=8)` beside `search_documents`, returning chunk
  excerpts with `path` and heading — the chat prompt is told to prefer it for open questions and
  to cite pages it then reads with `get_document` (sources stay "pages actually read").
- API: `GET /api/search?q=&mode=keyword|semantic|hybrid` (default `hybrid`: reciprocal rank
  fusion of both lists); `SearchResult` gains `excerpt` and `score`.
- Withholding: the index stores every page, but every query passes `allowed_paths` from the
  same readable view the chat and the API already compute; a withheld page can never be
  retrieved, and `withheld_paths` changing does not require a rebuild.
- Localised content (`docs/i18n/`) is indexed per language; a `lang` query uses that language's
  chunks and falls back to English, as the catalog does.

**Data.** `.librarian/index/` (state volume; rebuildable; nothing personal). Text leaves the
host only through the configured embedder — with `LocalEmbedder` it never does.

**Gates.** `semantic_search` is read-only (not in `MUTATING_TOOLS`); the embedder key is a
`SecretStr`; `doctor` gains an `embeddings` check (index present, model id, chunk count, age).

**Tests / criteria.** Chunker is deterministic; index rebuild touches only changed pages (hash
proof); withheld page absent from results for reader, chat tool and API (fail-first); hybrid
search finds "how do I get an API key for the gateway" when the page says "obtaining
credentials"; `FakeEmbedder` (hash-based vectors) keeps the suite offline; coverage ≥ 87%.

**Effort.** 2 loop-days. **Depends on.** Nothing. Feeds E, I, H.

### C. Ingestion agents ("scout") with the existing write gate

**Goal.** Knowledge born in Jira, pull requests and incident reviews reaches the KB as
proposed pages, reviewed by an owner, without anyone remembering to write.

**Design.**
- Sources are declared, never discovered: `kb.config.yaml` `sources:` — `{id, kind:
  jira|confluence|git|github, query|repo|space, section, owner, cadence}`. Reading tools per
  kind: the existing Confluence/Jira tools; `git_log`/`git_show` over a read-only clone path
  (`KB_SOURCE_GIT_ROOT`); `github_pulls` via `httpx` with a read-only token (`KB_GITHUB_TOKEN`).
  All read tools are in the tool server behind the gate; none mutates.
- New capability `scout` (`CAPABILITY_PROMPTS`): "for each declared source, find items since the
  last scout watermark, decide whether the KB is missing or contradicting something, and
  propose a page or an edit with the evidence".
- New mutating tool `propose_page(path, title, frontmatter, body, reason, sources)` and
  `propose_edit(path, body, reason, sources)`: they never write `docs/`. They record a
  `LibrarianAction` of type `proposal` whose *after* state (the full draft) goes to the snapshot
  directory, and add a `manual_review_needed` item — the console's review queue already renders
  those. Before recording, the draft runs through `checks/sensitive.py`; a critical hit drops the
  proposal and records a finding instead (the model never gets to "propose" a secret it read).
- Approval: a new operator action on the review queue, `POST /api/audits/{id}/actions/{aid}/apply`
  (operator, `reason`), applies the draft through `ActionLog` as a live write — subject to
  `KB_ALLOW_LIVE` like every write — or, in the recommended deployment, the weekly live job
  applies approved proposals and opens the PR, so git remains the last gate. The page owner from
  `sections` must be the approver or must have been @-mentioned (Jira comment) — recorded on the
  action as `approved_by` (pseudonymised the way `requested_by` is).
- Provenance: frontmatter `sources: [jira:AI-123, pr:repo#456]`; the `links` check verifies they
  resolve (when reachable); the page body carries a "Sources" section the agent must fill.
- Watermarks per source in `.librarian/scout/<id>.json` (last item id/time only).

**Data.** Drafts live under `.librarian/snapshots/` until applied; nothing personal beyond what
the source item already exposes internally.

**Gates.** Two new names in `MUTATING_TOOLS`; dry-run records and never writes; `apply` is the
only path to `docs/` and requires operator + live; the sensitive scanner runs on every draft;
Jira/GitHub tokens are read-only scopes (documented in `.env.example` and the sheet).

**Tests / criteria.** With fake Jira/git sources, a scout dry run produces a proposal with the
right section and sources and writes nothing under `docs/` (directory hash proof); a draft
containing a planted credential is refused with a finding; `apply` refuses without the live
gate, applies with it, and is reversible with `rollback_action`; watermark advances only on
success.

**Effort.** 3 loop-days. **Depends on.** Interface agreement on the proposal action shape (shared
with G and I). Feeds G, K.

### D. Feedback loops (insights)

**Goal.** Problem reports, reading behaviour and unanswered questions become one picture of
"which pages confuse people", for owners, the steward agent and the path planner.

**Design.**
- `kb_librarian/insights/` (new): `collect.py` aggregates per path — problem reports by
  category, views, distinct readers (from record files; counted, never listed), quiz attempts
  and fail rate per question, path drop-off (the step most readers stop at), chat hits (pages
  cited) and chat misses (turns that ended in a refusal or without sources). Any bucket with
  fewer than `k = 5` distinct readers is suppressed.
- Chat telemetry: `chat/runner.py` appends one record per turn to `.librarian/chat-log.jsonl`:
  `{ts, mode, lang, sources: [paths], refused: bool, cost_usd, duration_ms, persona}` — never the
  question or the answer. Retention: `KB_CHAT_LOG_DAYS` (default 90), pruned by `profiles purge`'s
  sibling `kb-librarian insights prune`.
- Output: `kb-librarian insights [--json]` writes `.librarian/insights/latest.json`; the nightly
  job runs it; `GET /api/insights` (operator) and an "Insights" tab on the Audits page (per
  section: top problem pages, failing questions, unanswered topics).
- Nudges: `nudges.ts` stays browser-side for dismissals, but the *candidates* come from the
  server (H) instead of local heuristics.

**Data.** Aggregates only; the chat log holds no text; the problems queue already holds reader
free text (kept as today, capped, operator-only).

**Gates.** Operator-only routes; `k`-anonymity enforced in the collector and tested; no new
write to `docs/`.

**Tests / criteria.** Collector suppresses a 4-reader bucket and reports a 5-reader one; a
withheld page never appears in insights; chat log line has exactly the agreed keys and no
message text (fail-first); the nightly job artifact contains `insights/latest.json`.

**Effort.** 2 loop-days. **Depends on.** Nothing. Feeds G, H.

### E. Librarian evaluation (golden set + nightly eval)

**Goal.** Every change to the prompt, tools, model or index gets a number: citation precision
and recall, answer correctness on a golden set, refusal correctness, cost and latency.

**Design.**
- `evals/golden.yaml` (≥ 50 items, grows with A): `{id, question, persona, lang, expect:
  {paths: [..], must_contain: [..], must_not_contain: [..], refuse: bool}, tags}`. Includes
  questions about withheld pages (must refuse), about topics not in the KB (must say so), in
  Spanish and Hebrew, and per persona.
- `kb-librarian eval [--items N] [--budget USD] [--json]`: runs every item through
  `run_chat` (the real path: gate, hooks, tools, index) with the configured model; computes per
  item citation precision/recall (sources vs `expect.paths`), keyword checks, refusal
  correctness, cost, duration; writes `.librarian/evals/<date>.json` and a Markdown summary;
  exits 1 when any threshold in `kb.config.yaml` `evals: {citation_precision: 0.8,
  refusal_correctness: 1.0, …}` is missed. A `--judge` option scores free-text answers with a
  second model call against a rubric (off by default; costs money).
- CI: `librarian-eval.yml` nightly, gated on the model secret like `live-smoke.yml`, with its
  own `KB_MAX_BUDGET_USD`; publishes the JSON as an artifact and posts the headline numbers into
  the job summary. A pull request that changes `chat/`, `retrieval/` or `evals/` runs a 10-item
  subset.
- Unit tests run the evaluator over `tests/fake_query.py` so the scoring is proven offline.

**Data.** Eval logs hold questions from the golden set (authored, not readers') and answers;
90-day retention on the state volume; never reader data.

**Gates.** Read-only path (the chat runner); budget ceilings; the job never sets `KB_ALLOW_LIVE`.

**Tests / criteria.** Scorer unit tests (precision/recall arithmetic, refusal logic) seen
failing first; a fake-query eval run produces the JSON and exit codes; the first real run
establishes the baseline recorded in the handover; thresholds enforced in CI.

**Effort.** 2 loop-days (+ golden-set authoring with owners). **Depends on.** B for the index
numbers to mean anything; runs without it.

### F. Operational leftovers from v4

| Item | Action | Owner | Effort |
| --- | --- | --- | --- |
| Review completion | Re-run the workflow's frontend, deploy, i18n/docs and merge-integrity lenses with adversarial verification, and the harness auditor; fix findings | build session | 0.5 day |
| Security sign-offs | `kb-librarian security submit <module>` for all 24; reviewers `sign`; then `security verify` in the release job and a CODEOWNERS rule for `security/` | security team | reviewer time |
| Cluster parameters | Set the ingress namespace label, `FORWARDED_ALLOW_IPS`, and narrow egress 443 (`to:` blocks or FQDN policy); first `kubectl apply` in a staging namespace with the RUNBOOK | platform | 0.5 day |
| Translation notice | Decide: a per-page "machine-translated" banner (one string × 10 locales, driven by a frontmatter flag the translate job sets) or none | product | 0.25 day |
| Shared key retirement | Once every operator signs in through a group: unset `KB_API_KEY`; `doctor` reports "no break-glass key" | platform | 0 |
| Subject in the server log | Privacy function decides; if refused, log the pseudonym only and keep the mapping in a sealed operator note | privacy | decision |
| Image digests | Pin base and app image digests after the registry scan; `validate_k8s` accepts the `tag@sha256` form already | platform | 0.25 day |

### G. Owner-facing review agent ("steward")

**Goal.** Each section owner gets, weekly, one digest with a proposed edit for every item:
pages due for review, problem reports, failing quiz questions, unanswered topics.

**Design.**
- Capability `steward`: inputs are the freshness findings (`checks/freshness.py`), the problems
  queue, `insights/latest.json` (D) and the scout's open proposals (C). For each section it
  drafts the digest and, for each item, a proposal through `propose_edit` (C) — e.g. a rewrite of
  the paragraph readers report as unclear, with the evidence cited.
- Delivery through existing tools: `jira_create_issue` (one issue per owner per week, labelled,
  linking the console's review queue) or `confluence_comment` (new read/write pair on the
  mirrored page). Both are write tools behind `KB_ATLASSIAN_ALLOW_WRITE` + live, as today.
- One-click approval: the Jira issue links to the console review queue where the operator
  applies (C's `apply`) — the owner approves in Jira (a comment `approve <action-id>` that the
  next steward run reads and turns into the `approved_by` field), the operator applies. Where the
  owner is an operator by group, the console button is the click.
- Schedule: `librarian-weekly-live.yml` gains `--capabilities steward` in a second job that
  runs dry-run always and live only when the repository variable allows Atlassian writes.

**Gates.** No new write to `docs/`; Atlassian writes stay double-gated; the digest never quotes a
reader's free text verbatim (it summarises; the queue has the original for the operator).

**Tests / criteria.** A dry-run steward over a fixture with one stale page, one problem report
and one failing question produces one digest per owner with three proposals and creates no
Jira issue; with the write gate on, the fake Jira transport receives exactly one issue per
owner; the approval comment parser accepts only `approve <id>` from the page's owner.

**Effort.** 2 loop-days. **Depends on.** C (proposal actions), D (insights).

### H. Adaptive persona learning paths

**Goal.** The reader's next three pages and next quiz follow what they have read and what they
got wrong; owners see where many readers fail the same question.

**Design.**
- Deterministic planner first: `GET /api/profile/path` returns the reader's path (A), position,
  the next three steps, and the checkpoint state, computed from `viewed` and `quizzes` — no model
  call. Home shows "Your path" instead of the heuristic nudges; the nudge strip's candidates come
  from this endpoint (dismissals stay local).
- Remediation by the agent: quiz results record the *question ids* failed (the quiz card already
  grades locally; `POST /api/profile/quizzes` gains `failed: [ids]`, bounded); a chat mode
  `tutor` asks the librarian to explain exactly those questions from the page, and the planner
  inserts the relevant page (or its section) before the checkpoint again.
- Owner signal: D's insights show fail rate per question (k-anonymous); G's steward proposes a
  rewrite when a question fails for > 40 % of ≥ 10 readers.
- Persona switch re-plans; the persona picker shows path length and estimated time (frontmatter
  `reading_minutes`, checked by `paths`).

**Data.** Question ids per quiz result (no answers chosen, as today).

**Gates.** Per-user routes (`require_user`), same-origin; the tutor mode is the same read-only
runner; withheld pages are never planned.

**Tests / criteria.** Planner unit tests (fresh reader → first three steps; two steps read →
next three; failed checkpoint → remediation step inserted; withheld step skipped); console tests
for "Your path"; strings in 10 locales; a signed-in 360 px probe.

**Effort.** 2 loop-days. **Depends on.** A (paths config), D (insights) for the owner signal.

### I. Authoring copilot in the console

**Goal.** On any page an author can ask for a draft update from a source, a policy check, or a
section quiz, and turn the result into a proposed edit without leaving the audit trail.

**Design.**
- Chat modes `draft` (context: page + a pasted source excerpt ≤ 4 000 chars or a `sources:`
  reference), `check` (context: page + a governance page id; the runner reads both and reports
  contradictions with citations) and `quiz-section` (the existing quiz mode over a heading).
- Output of `draft` is a proposed body; the console renders a **diff view** (new
  `ProposedDiff.tsx`, plain-text line diff, no HTML) with "Propose" → `POST /api/pages/{path}/
  proposals` (signed-in author, same-origin) which records `propose_edit` as a dry-run action
  under a new audit of type `authoring` — the operator applies from the review queue (C).
  Authors never write `docs/` directly; group operators can apply their own proposals only when
  a second person approved (`approved_by` ≠ `requested_by`).
- The selection toolbar gains "Draft an update" and "Check against policy" beside the three
  existing actions when the reader has the `author` persona flag (frontmatter-driven: page owners
  and `audience: contributor`).

**Gates.** The runner stays read-only; the only write is the proposal action; the sensitive
scanner runs on every draft; per-client and daily chat ceilings apply; sources pasted by the
author are bounded and enveloped like selections.

**Tests / criteria.** `draft` returns a body and the console shows a diff; "Propose" records an
action and writes nothing (hash proof); a draft with a planted secret is refused; `check` cites
the governance page; four-eyes rule enforced in tests; strings in 10 locales.

**Effort.** 2 loop-days. **Depends on.** C (proposal actions). Better with B.

### J. Executable skills

**Goal.** `docs/skills/*/SKILL.md` become playbooks an internal Claude Code user can invoke, and
the librarian proves nightly that each still runs.

**Design.**
- SKILL frontmatter gains `runnable: true`, `inputs:`, `steps: [{run, dry_run, expect}]` where
  `dry_run` is the harmless variant of each command and `expect` a substring or exit code.
- `kb-librarian skills validate [--live]`: runs every runnable skill's `dry_run` steps in a
  temporary directory with a scrubbed environment (no `KB_*` secrets, no network unless the step
  says `network: true`), records a report; the nightly job runs it and fails on a broken skill.
- `kb-librarian skills export --to <dir>` writes each skill as a Claude Code skill directory
  (`SKILL.md` with the frontmatter Claude Code expects, resources copied), so "paved roads" are
  installable by engineers; the KB is the single source.
- The `structure` check verifies every runnable skill has at least one step and a `dry_run`.

**Gates.** Steps run only in dry-run by default; `--live` requires `KB_ALLOW_LIVE` (the same gate,
same reason: a skill step may change something); the runner never executes a step from a
withheld or `draft` page.

**Tests / criteria.** A fixture skill with a failing `expect` fails validation (seen failing
first); export produces a directory Claude Code loads (a structural test on the frontmatter);
the eight skills from A validate nightly.

**Effort.** 1.5 loop-days. **Depends on.** A's skills.

### K. Media ingestion

**Goal.** Recorded talks and tutorials become pages with timestamps; the video catalog stops
being placeholders; recordings never leave the bank.

**Design.**
- `kb-librarian media transcribe <id> [--provider]`: downloads the recording from the internal
  video platform URL in `catalog.yaml` (`KB_MEDIA_TOKEN`), sends audio to the configured
  speech-to-text (`Transcriber` protocol: `HttpTranscriber` for an on-prem Whisper-compatible
  endpoint, `KB_STT_URL`; a `LocalTranscriber` extra), stores `.librarian/media/<id>.json`
  (segments with timestamps) — never under `docs/`.
- Capability `media`: for a transcribed id, draft a tutorial page (`propose_page`, C) with a
  summary, sections keyed by timestamp (`[12:30]` links to `url#t=750`), and the catalog entry's
  `status` proposed as `available`. The sensitive scanner runs on the transcript before the model
  sees it; a critical hit stops the pipeline with a finding (speakers say secrets aloud).
- `catalogs` check learns `transcript: true|false` and warns when an `available` video has none.

**Gates.** Proposal-only writes; the transcript text goes to the model only through the
configured provider path (a policy decision recorded in the sheet); recordings themselves are
never sent anywhere but the transcriber.

**Tests / criteria.** Fake transcriber → segments JSON; a proposal with timestamps; catalog check
warns on a missing transcript; scanner stops a planted secret.

**Effort.** 2 loop-days. **Depends on.** C.

### L. Policy-aware guardrails as a service

**Goal.** Other internal agents ask the KB "may I publish this?" before they do; the KB's
sensitive-content rules and withholding become the organisation's control point.

**Design.**
- `POST /api/guard/check {text, tier}` → `{allowed, findings: [{rule, severity, span}],
  redacted}`; `POST /api/guard/redact` → the text with spans replaced. Backed by
  `checks/sensitive.py` (extended with per-tier rule sets from `kb.config.yaml` `guard:`) and, for
  quoted KB content, the withholding list (a caller quoting a withheld page is refused).
- Auth: service tokens (`KB_GUARD_TOKENS`, comma-separated, each ≥ 32 chars, compared in constant
  time) or the platform's mTLS at the ingress; per-token throttle; body cap 64 KB as today.
- Nothing is stored: the endpoint logs counts and rule ids only; the text is never written.
- Clients: an OpenAPI tag, a ten-line Python snippet in `docs/integrations/guard.md`, and a
  Claude Code hook example (`PreToolUse` on publish tools) so internal agents call it.

**Gates.** Read-only; no reader data; tokens are secrets; the rule set is versioned with the
contract so a caller can pin `tier`.

**Tests / criteria.** Planted credential/PII/customer data refused per tier; withheld quote
refused; 401 without a token, 429 on flood; no text in the access line (fail-first); latency
< 50 ms on a 64 KB body.

**Effort.** 1.5 loop-days. **Depends on.** Nothing.

---

## 4. Plan

Four phases, each run as parallel loops in sparse worktrees bound by an interface file (as in
v4), each ending with the panel review, the harness reviewer, a handover version and a push.

| Phase | Loops in parallel | Interface to agree first | Exit criteria | Handover |
| --- | --- | --- | --- | --- |
| **1 — Measure and retrieve** (≈ 1 week) | F leftovers · B retrieval · E eval · D insights | `Embedder` protocol; chat-log record; `insights/latest.json` schema; eval item schema and thresholds | hybrid search live; first eval baseline recorded; insights on the Audits page; sign-offs submitted; staging apply done | v5 |
| **2 — Propose and approve** (≈ 1.5 weeks) | C scout · I copilot · G steward | Proposal action shape (`proposal` type, snapshot layout, `approved_by`, `apply` route); `sources:` frontmatter; Jira issue format | a scouted proposal applied through the queue and reverted; an author's draft proposed and applied under four eyes; one weekly digest delivered to a fake Jira | v6 |
| **3 — Teach** (≈ 2 weeks, content-heavy) | A content (per section, with owners) · H paths · J skills | `paths:` config schema; checkpoint page frontmatter; quiz `failed` ids; runnable SKILL frontmatter | every persona has a path to a checkpoint; "Your path" on Home; eight skills validate nightly and export | v7 |
| **4 — Media and control point** (≈ 1 week) | K media · L guard | `Transcriber` protocol; guard API and tiers | one recording transcribed to an applied page; guard called from a sample agent hook | v8 |

Ordering rationale: B and E first because they make every later change measurable; C before
G and I because all three share the proposal mechanism; A before H and J because paths and
runnable skills need the content; K and L last because they add providers and an external
surface, which the security team should review with the earlier sign-offs in hand.

Estimated total: ~24 agent-loop days plus owner time for content, golden questions and ADRs.

## 5. Decisions the bank must take

1. **Embedding provider**: on-prem model (text never leaves) versus an external API under a
   data-processing agreement. B ships both; the default should be the on-prem one.
2. **Speech-to-text provider** and whether transcripts may go to the model at all (K).
3. **Chat telemetry**: paths and refusal flags only (default) or hashed questions for a period.
4. **Approval policy**: is the page owner's Jira comment sufficient, or must an operator click?
5. **Subject in the server log** at audit start (v4 leftover).
6. **Guard tiers**: which rule sets apply to which internal agents, and who owns the rule set.

## 6. Risks

- **Content is the long pole**: agents draft, owners approve; without owner time Phase 3 slips.
  Mitigation: scout (C) and steward (G) reduce the writing to reviewing.
- **Model cost**: eval, scout and steward add scheduled model calls; each carries a ceiling and
  the daily ledger pattern; the eval baseline shows the cost per run before it is scheduled.
- **Retrieval leakage**: an index that ignored withholding would be the worst regression the KB
  could have; B's fail-first test on withheld pages is mandatory before merge, and the review
  lens for security must run (F).
- **Proposal fatigue**: a scout that proposes too much trains owners to ignore it; cap proposals
  per section per week and rank by evidence; measure approval rate in insights.
- **Provider lock-in**: the two protocols (`Embedder`, `Transcriber`) with a local implementation
  keep the bank in control; the sqlite index is rebuildable from pages at any time.
