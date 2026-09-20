# Security review sheet: Insights (chat telemetry, collector, CLI and operator endpoint)

| | |
| --- | --- |
| Module id | `insights` |
| Kind | backend |
| Code | `kb_librarian/insights/` (`models.py`, `collect.py`, `store.py`), `kb_librarian/chat/telemetry.py`, `kb_librarian/cli_insights.py`, `kb_librarian/api/routes_insights.py` |
| Tests | `tests/test_telemetry.py`, `tests/test_insights.py`, `tests/test_insights_api.py`, `tests/test_cli_insights.py` |
| Depends on | `profile` (reader records, read for counts only), `api-pages` (problem reports), `api-chat` (records the telemetry), `api-core` (`require_operator`, `same_origin`, withholding), `catalog` |

## Purpose

One picture of "which pages confuse people" for owners and operators: per readable page, the
problem reports by category, views and distinct readers, quiz attempts and fail rate, and how
often the chat cited the page; plus the unanswered questions (chat turns that ended without a
source) counted by mode and by language. Aggregates only — paths, counts and rates — under
k-anonymity.

## Entry points

- `chat/telemetry.py`: `record(root, *, mode, lang, persona, sources, refused, cost_usd, duration_ms)`
  appends one JSON line to `.librarian/chat-log.jsonl`; `read(root, since)` yields the well-formed
  lines since a moment; `prune(root, days)` rewrites the file without older lines. Called from
  `POST /api/chat` after every turn (success and 502 alike), through `run_in_threadpool`.
- `insights/collect.py::collect(root, config, catalog, withheld, *, k, window_days, now)` →
  `Insights`; `insights/store.py::write(root, insights)` / `read(root)` for
  `.librarian/insights/latest.json`.
- `kb-librarian insights [--json] [--window-days N]` (`cli_insights.py`) regenerates and writes the
  file, then prints the top pages by problems, by quiz fail rate, and the unanswered counts;
  `kb-librarian insights prune` drops telemetry lines older than `KB_CHAT_LOG_DAYS` (default 90).
- `GET /api/insights` (operator) returns the stored file, minus any page withheld *now*; 404 with a
  fixed message until one was generated. `POST /api/insights/refresh` (operator + `same_origin`)
  regenerates on the threadpool and returns the result.

## Trust boundaries

- The telemetry line is written by the server from the turn it just ran: `mode` and `lang` are
  the validated request fields, `sources` the paths the runner derived from its own tool trail,
  `persona` the signed-in reader's stored persona (never a request field), `refused` and
  `cost_usd` the runner's result. Nothing of the caller's text reaches the line.
- The collector reads three server-owned stores (reader records, problem files, the chat log) and
  the catalog; it takes the withheld set from the caller (`service.withheld_paths`, the same
  verdict the reader API uses) and additionally drops any `Document.sensitive` page, so a withheld
  page is never a key in the output. `GET /api/insights` re-applies the current withheld set to
  the stored file, so a page withheld after generation is not served either.
- Both routes need the operator role; the refresh, a state-changing POST, also passes
  `same_origin` for every caller (a cross-site browser request is refused with 403 even with a key).
- The CLI runs as the invoking user on the state volume, like `profiles purge`.

## Data handled

**Chat telemetry** (`.librarian/chat-log.jsonl`, runtime state, never committed): per turn exactly
`ts, mode, lang, persona, sources, refused, cost_usd, duration_ms`. It holds **no** question, no
answer, no selection, no history, no client address, no subject, name or e-mail, no request id.
`persona` is one of the contract's audience values (or `null`); `sources` are page paths (readable
pages, since the runner cannot read a withheld page). Retention `KB_CHAT_LOG_DAYS` via
`insights prune` (the deployment schedules it next to `profiles purge`).

**Insights** (`.librarian/insights/latest.json`): `{generated_at, k, window_days, pages: {path:
{views, readers, problems: {category: n}, quiz_attempts, quiz_fail_rate, chat_citations}},
unanswered: {mode: {…}, lang: {…}}, suppressed}`. Reader records are read for counts only:
a distinct reader is counted (never listed, hashed or named), and for a page with fewer than `k`
(`KB_INSIGHTS_K`, default 5) distinct readers in the window every reader-derived number — `views`,
`readers`, `quiz_attempts`, `quiz_fail_rate` — is `null`; problem counts and chat citations are not
derived from records and stay. `suppressed` is the number of such pages. A page with no activity
in the window does not appear. Problem *messages* are never read into the output (category and
path only).

## Secrets

None.

## External calls

None: local files only (`.librarian/users/`, `.librarian/problems/`, `.librarian/chat-log.jsonl`,
`.librarian/insights/`).

## Mutations

Appends to the chat log; rewrites the chat log (prune) and the insights file, both through a
temp file + `os.replace`. Never a page, never a reader record, never a problem file. Nothing goes
through `ActionLog` because nothing under `docs/` changes.

## Controls in place

- Telemetry: fixed key set built in code (a test asserts the exact keys and that the question,
  answer, selection and client are absent); the append is one `O_APPEND` write under a process
  lock; a telemetry failure is logged by exception type and never fails the chat request.
- `read` skips malformed lines, lines without an aware timestamp, and anything that is not an
  object; `prune` drops those as well, and leaves no temp file on failure.
- k-anonymity is enforced in the collector (`_page_insight`) and tested at `k-1`, `k` and `k+1`.
- Records are enumerated through `profile.retention.records` (regular files, symlinks never
  followed) and a record that does not parse is skipped, as the purge does; problem files likewise.
- The window applies to every source on its own timestamp (visit `last_at`, quiz `at`, problem
  `at`, line `ts`); a naive timestamp is outside every window.
- CLI output is paths and numbers only; the JSON is the stored file verbatim.
- Routes: `require_operator` on both; `same_origin` on the refresh; the collector runs on the
  threadpool; 404 text is fixed.

## Residual risks and reviewer attention points

- `views` is a sum of per-reader counts and `readers` a distinct count, both only for pages at or
  above `k`; an operator who can also read `.librarian/users/` directly gains nothing from the
  aggregate. The threshold is a deployment choice (`KB_INSIGHTS_K`); a page just at `k` with one
  problem report from a known reader is the classic small-bucket risk — raise `k` in small teams.
- `unanswered` counts by `lang` and `mode` are not per page and carry no reader dimension.
- The chat log grows with use until `insights prune` runs; the scheduled job is the retention
  control, as for reader records.
- The refresh reads every record and problem file on each call; it is operator-only and runs on
  the threadpool, but a large deployment should prefer the nightly CLI run and the GET.

## Reviewer checklist

- [ ] `telemetry.record` is called with the runner's result and the stored persona only; no field
      comes from request text.
- [ ] The line keys are exactly the eight agreed ones; no test writes a message into the log.
- [ ] `_page_insight` nulls every reader-derived field below `k`; `suppressed` counts those pages.
- [ ] `collect` takes the withheld set from `service.withheld_paths` in both the CLI and the API,
      and the GET re-filters against the current set.
- [ ] `POST /api/insights/refresh` depends on `require_operator` and `same_origin`.
- [ ] `insights prune` uses `KB_CHAT_LOG_DAYS` and prints a count only.

## Sign-off

Submit with `kb-librarian security submit insights`; the reviewer records the decision with
`kb-librarian security sign insights …`, which appends a row here and to `security/signoffs/insights.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
