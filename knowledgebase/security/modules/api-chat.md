# Security review sheet: Chat endpoint

| | |
| --- | --- |
| Module id | `api-chat` |
| Kind | backend |
| Code | `kb_librarian/api/routes_chat.py` |
| Tests | `tests/test_api_chat.py`, `tests/test_api_chat_modes.py` |
| Depends on | `api-core`, `chat` |

## Purpose

`POST /api/chat` — one librarian answer for a reader's question, open to any role (like search),
and the three page actions (explain / elaborate / quiz me) the console's selection toolbar sends.

## Entry points

`POST /api/chat` with `{message, history[], lang?, mode?, context?}` → `{answer, sources[]}`,
plus `quiz[]` (and an empty `answer`) when `mode` is `quiz`. 429 with the fixed message
`the librarian's daily chat budget is spent; try again tomorrow` once today's chat spend has reached
`KB_CHAT_DAILY_BUDGET_USD`.

## Trust boundaries

Unauthenticated callers. The body is untrusted text forwarded to the model as the user turn
(see the `chat` sheet for prompt placement). `context.selection` is page text the reader chose
(or typed: the API cannot tell) and is forwarded verbatim within its size limit.

The `context.path` must name a page the caller may open: unknown paths **and withheld pages**
(by current text or by the latest audit's finding) are both 404 through the shared
`service.readable_page`, the same lookup `POST /profile/views` uses, so the endpoint is no
oracle for withheld pages. The `title` the client sends is size-checked and otherwise unused:
the prompt takes the **catalog's** title, so the only client text that reaches the prompt is
the message, the history and the selection (inside its data envelope).

## Data handled

Question (1–2000 chars), history (≤ 16 turns, each 1–4000 chars, role `user|assistant`),
`lang`, `mode` (`ask|explain|elaborate|quiz`, default `ask`), `context` (`path` 1–400,
`title` ≤ 200, `selection` ≤ 2000). Nothing of the exchange is persisted and no report is saved;
what is written is the turn's cost (`ChatAnswer.cost_usd`), added to the day-keyed spend
ledger `.librarian/chat-spend.json` (`chat/spend.py`: totals per UTC day, no message, no client id),
and one telemetry line (`chat/telemetry.py`, reviewed under `insights`) with exactly
`ts, mode, lang, persona, sources, refused, cost_usd, duration_ms` — the persona read from the
signed-in reader's record (`current_user`, `null` when anonymous), the sources from the runner's
trail, never the message, the answer, the selection or the client. The line is written after the
turn for a success and a 502 alike, on the threadpool, and a failure to write it is logged by
exception type and never fails the request.
Quiz answers never reach this endpoint (graded in the browser; see `profile` for what is stored).

## Secrets

None.

## External calls

The model API, via `run_chat`.

## Mutations

None possible (read-only tool set in `chat`).

## Controls in place

- Pydantic limits on every field; an action mode without a `context` is 422; `BodyCap` 64 KiB upstream.
- Context path resolved against the catalog and the withheld set before the runner is called,
  on the threadpool (`run_in_threadpool`): the catalog's change stamp is a stat sweep over
  every page and must not run on the event loop.
- Throttle: 10 messages per client per minute (`_throttle`, keyed on `request.client.host`,
  buckets pruned); 429 beyond — the actions count like messages.
- Runner errors (including a malformed quiz) map to 502 with the runner's message (no stack traces).
- Daily ceiling: before the context is resolved or the model called, today's total from the ledger
  (`ledger_for(state.root).today_total()`, read on the threadpool) is compared with
  `KB_CHAT_DAILY_BUDGET_USD` (default 25); at or above it the request is 429 with a fixed message.
  After the turn, `cost_usd` is added whenever the SDK reported one — also for an errored turn, so a
  billed failure counts. The ceiling and the message come from settings and code; nothing in the body
  can change them.

## Residual risks and reviewer attention points

- Cost exposure from anonymous callers is bounded per client per minute, per turn
  (`KB_CHAT_MAX_BUDGET_USD`) and now per day for all clients together (`KB_CHAT_DAILY_BUDGET_USD`).
  The ledger is checked before a turn and updated after it, so turns in flight at the ceiling can
  overshoot by their own per-turn caps; and a distributed caller can spend the day's budget for
  everyone (denial of chat, not unbounded spend).
- Answers are model-authored text rendered as plain text by the widget (no Markdown, no links
  other than the derived sources). Quiz questions and options are likewise rendered as text.

## Reviewer checklist

- [ ] Field limits unchanged or justified; throttle constants reviewed for the deployment.
- [ ] No caller-supplied ceiling/model/tool parameters are accepted (`mode` and `context` shape the prompt only).
- [ ] `_resolve_context` goes through `service.readable_page` and takes the title from the catalog.
- [ ] The daily ceiling is checked before `run_chat` and the cost recorded after it, error or not; the 429 text is fixed.
- [ ] `_record_turn` passes only the runner's result, the validated `mode`/`lang` and the stored persona to
      `telemetry.record`; no request text, no client address.

## Sign-off

Submit with `kb-librarian security submit api-chat`; the reviewer records the decision with
`kb-librarian security sign api-chat …`, which appends a row here and to `security/signoffs/api-chat.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
