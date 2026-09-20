# Security review sheet: Reader profiles (progress, persona, quiz results)

| | |
| --- | --- |
| Module id | `profile` |
| Kind | backend |
| Code | `kb_librarian/profile/store.py`, `kb_librarian/api/routes_profile.py` |
| Tests | `tests/test_profile.py`, `tests/test_profile_retention.py` |
| Depends on | `auth` (`require_user`), `api-core` (`AppState.profiles`, withholding) |

## Purpose

What the knowledge base remembers about a signed-in reader: the pages they opened (path,
first/last time, count), the persona they chose, and quiz results. It drives "continue reading",
per-section progress, persona-based ordering of the console and the browser-side nudges.

## Entry points

`GET /api/profile` (profile + per-section progress + the selectable personas),
`PUT /api/profile/persona`, `POST /api/profile/views {path}`,
`POST /api/profile/quizzes {path, score, total}`, `DELETE /api/profile` (forget me).
All require a signed-in reader (`require_user` → 401 otherwise).

## Trust boundaries

- The **subject comes from the session cookie only**; no route accepts a subject, so a reader can
  only ever read, change or delete their own record. Without SSO configured, the routes are
  unreachable (401 for everyone). `require_user` includes the `same_origin` CSRF guard, so a
  foreign site cannot drive these routes through a signed-in browser.
- The body of a view or a quiz result is a page path validated against the catalog
  (`_readable_page`); a page that does not exist **or is withheld** is refused (404) and never
  recorded, so the profile cannot be used to learn that a withheld page exists.
- The persona must be one of the contract's `audience_values` (minus `everyone`).
- A quiz result is **self-reported**: the console grades the quiz in the browser and posts only
  the tally (`0 ≤ score ≤ total`, `1 ≤ total ≤ 10`). The server cannot verify it and does not
  try; it is the reader's own progress record, not an assessment of record.

## Data handled

**Personal data (reading behaviour)**: page paths with timestamps and counts, persona, quiz
tallies (`path`, `at`, `score`, `total` — never the questions, the options or the answers
chosen). No page text, no free text from the reader, no e-mail/name (those live only in the
session cookie). The insights collector (`insights/collect.py`, reviewed under `insights`) reads
these records for counts only — views summed, distinct readers counted, quiz tallies — and reports
nothing about a page with fewer than `k` readers (k-anonymity); it never lists, names or hashes a
reader. Stored as `.librarian/users/<sha256(issuer + "\0" + sub)>.json` — keyed by the
issuer-qualified subject (`sub` is unique only per issuer; the raw value never becomes a path
component), so the file name reveals no identity and is not enumerable; `.librarian/` is runtime
state on a protected volume and never committed.

**Session epoch** (`Profile.session_epoch`, default 0): the value a session cookie must carry to
be accepted, read on every cookie-authenticated request (`ProfileStore.session_epoch`, under the
store lock) and moved by `POST /api/auth/logout-everywhere` (`bump_session_epoch`: under the lock,
saved, so `updated_at` moves). The new value is derived from the clock — `max(old + 1,
int(time.time()))` — rather than a bare counter, so a value can never recur across records or
restarts. `delete` (`DELETE /api/profile`) removes every reading field but keeps a **tombstone**
holding only the epoch when one was ever bumped, so a cookie issued before the first "sign out
everywhere" (epoch 0) can never be accepted again. A record that cannot be parsed is replaced by a
tombstone with a fresh **nanosecond** epoch (`store.load`; logged by hashed stem), so revocation
fails closed rather than reading as 0; `save` fsyncs before the rename so a crash cannot leave a
zero-length record. Retention (`purge`, `revoked_until` = the session TTL ago) never removes a
record holding an epoch until every cookie from before that bump has expired. The epoch is not
personal data: an integer with no link to reading behaviour, and the only field a record may hold
for a reader who never opened a page.

## Secrets

None.

## External calls

None.

## Mutations

Writes to the reader's own JSON record (atomic temp-file + rename, serialised by a process
lock). History capped at 500 pages and quiz results at 200 (oldest dropped, `MAX_VIEWED` /
`MAX_QUIZZES`). `DELETE` removes the file.

**Retention** (`ProfileStore.purge`, driven by `kb-librarian profiles purge`): a record whose
`updated_at` — refreshed by every view, persona change and quiz tally, so the measure is
inactivity — is older than the cut-off is removed. The command is dry-run by default and prints
counts only; `--live` is required to delete and is deliberately not behind `KB_ALLOW_LIVE` (that
gate protects pages from the model's write tools; a purge never touches a page). The cut-off comes
from `--older-than-days` or `KB_PROFILE_RETENTION_DAYS`; with neither the command refuses (exit 2),
so an unconfigured deployment purges nothing. The purge (`profile/retention.py`) takes the store
lock, decides on `updated_at` and, for a record holding a revocation epoch, also on the session
TTL (`revoked_until`: such a record stays until every cookie from before the bump has expired),
skips files it cannot parse (and records without a timezone), never follows a symlink, counts a
record it cannot unlink instead of naming it (`PurgeResult.failed`); the hashed stems it returns
are for callers and tests, never printed. `stats` reports a count and the oldest/newest
`updated_at` and nothing that identifies a reader. The schedule itself belongs to the deployment.

## Controls in place

- `require_user` on every route; subject never from input; validation on path length (≤ 400),
  persona, and the quiz tally's ranges (a score above the total is 422).
- Views of pages that no longer exist are hidden from the API response (but remain on disk
  until the reader deletes their data or the cap evicts them).
- A corrupt record is treated as empty, not as an error that leaks its content.
- Reader-facing deletion ("Delete my data") in Settings; documented in the Identity card.

## Residual risks and reviewer attention points

- Reading history is personal data under most privacy regimes. Retention is inactivity-based and
  only as good as the deployment's schedule: an instance that never runs `profiles purge --live`,
  or runs it without `KB_PROFILE_RETENTION_DAYS`, keeps records until the reader deletes them.
- Records are per API instance on the state volume; a multi-instance deployment needs shared
  storage or sticky routing (the same is true of reports today).
- No rate limit on `POST /profile/views` or `POST /profile/quizzes` beyond the 64 KiB body
  cap: a signed-in reader can write at request rate to their own record only, whose size is
  bounded by the two caps.

## Reviewer checklist

- [ ] Every route depends on `require_user`; no route reads `sub` from the body or query.
- [ ] `record_view` and `record_quiz` re-check withholding through `_readable_page` / `service.readable_page`.
- [ ] Only `{path, score, total}` of a quiz is stored; no question or answer text.
- [ ] Retention period (`KB_PROFILE_RETENTION_DAYS`) agreed with the privacy function and scheduled.
- [ ] `purge` removes nothing in dry-run, needs an explicit `--live`, decides on `updated_at` only
      and never follows a symlink; no CLI output names a subject or a hashed stem.

## Sign-off

Submit with `kb-librarian security submit profile`; the reviewer records the decision with
`kb-librarian security sign profile …`, which appends a row here and to `security/signoffs/profile.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
