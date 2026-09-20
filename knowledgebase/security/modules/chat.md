# Security review sheet: Librarian chat turn

| | |
| --- | --- |
| Module id | `chat` |
| Kind | backend |
| Code | `kb_librarian/chat/` (`runner.py`, `prompts.py`, `quiz.py`, `spend.py`) |
| Tests | `tests/test_chat.py`, `tests/test_chat_modes.py`, `tests/test_spend.py`, `tests/test_retrieval_chat.py` |
| Depends on | claude-agent-sdk, `agent/`, `tools/`, `retrieval` |

## Purpose

One short, capped agent turn that answers a reader from the knowledge base:
`run_chat(settings, root, message, history, lang=, mode=, context=, query_fn=)` →
`ChatAnswer(answer, sources, error, quiz, cost_usd)`. Used by `POST /api/chat`. No report is saved.
`spend.py` keeps the day-keyed spend ledger the endpoint's daily ceiling reads and updates.

Four modes. `ask` is a free question. `explain`, `elaborate` and `quiz` are the actions a reader
triggers on a page (from text they selected, or the whole page): explain the passage in plain
language; go deeper (background, related pages via search, pitfalls); or write exactly three
multiple-choice questions as strict JSON. All three need a `ChatContext(path, title, selection)`.

## Entry points

`run_chat`, `build_chat_prompt(history, message, mode=, context=)`, `context_block`,
`CHAT_SYSTEM_PROMPT`, `quiz.parse_quiz(text)`, `spend.SpendLedger(path).today_total()` / `.add(cost_usd)`,
`spend.ledger_for(root)` (one ledger and lock per root at `.librarian/chat-spend.json`).

## Trust boundaries

- The **question, history and context are untrusted** (any reader, unauthenticated). They are
  placed in the user prompt, never in the system prompt; the history is a transcript the model is
  told to treat as conversation, not instructions with authority.
- The **selection is reader-chosen page text** (up to 2000 characters) that is sent to the model.
  It travels inside a `<selection>` envelope the prompt labels as quoted page text (rule 2 of the
  system prompt), a stray `</selection>` inside it is dropped so the envelope closes where the
  prompt says, and the reader may of course type anything there — it carries no more authority
  than the question itself.
- Page content returned by tools is wrapped in the `<kb-data>` envelope (`tools/context.py`).
- The context page must be in the chat's readable catalog (`_readable`, see below); otherwise the
  turn ends with an error before the model is called. The API has already refused it with 404.

## Data handled

The question, prior turns (the API accepts up to 16; the runner forwards the last 8), the
context page path/title/selection, the pages the model reads, the answer. Nothing persisted.
`sources` are derived from **successful `get_document` calls in the tool trail**, so a citation
is always a page that was actually read.

A `quiz` reply is parsed defensively (`quiz.py`): code fences stripped, first `{` to last `}`,
then validated as 1–5 questions, each with 2–6 non-empty options, a 0-based `answer` inside the
options and an optional `why`. Anything else is `ChatAnswer.error` (502), never a partial quiz.
Quiz **answers are never seen by this module**: grading happens in the browser.

`cost_usd` is `ResultMessage.total_cost_usd` (a finite, non-negative number or `None`), carried on
every `ChatAnswer` — an errored result included, since the turn was billed. The ledger file holds
`{"YYYY-MM-DD": total}` (UTC days) for the last 31 days and nothing else: no message, no client, no identity.

**Telemetry** (`chat/telemetry.py`, reviewed under `insights`; the runner itself writes nothing).
After every turn `POST /api/chat` appends one JSON line to `.librarian/chat-log.jsonl` holding
exactly `ts, mode, lang, persona, sources, refused, cost_usd, duration_ms`: the timestamp, the
request's validated `mode` and `lang`, the signed-in reader's stored persona (or `null`), the page
paths the runner derived from its tool trail, whether the turn ended without a source and without
an error, the billed cost and the wall time. A line never holds the question, the history, the
selection, the answer, the quiz, the client address, a subject, a name or a request id. Lines older
than `KB_CHAT_LOG_DAYS` are dropped by `kb-librarian insights prune`.

## Secrets

None; the system prompt forbids repeating credentials/personal/customer data found in pages
(rule 6), in every mode.

## External calls

The model API only.

## Mutations

None possible: only `build_read_tools(ctx)` is offered; `GatePolicy` allows just those
qualified names; `DISALLOWED_BUILTINS` applied; `tools=[]`, `allowed_tools=[]`,
`strict_mcp_config=True`, `setting_sources=[]`. The modes change the user prompt only.

## Controls in place

- Separate, small ceilings: `KB_CHAT_MAX_TURNS` (6) and `KB_CHAT_MAX_BUDGET_USD` (0.5), for every mode.
- `lang` is only honoured when it is in `config.i18n.languages` (localized catalog); otherwise English.
- A `ResultMessage.is_error`, missing answer or malformed quiz becomes `ChatAnswer.error` (the API maps it to 502).
- An unknown mode, or an action mode without a context page, is a `ValueError` in `build_chat_prompt`.
- Hooks record the trail in-memory for source extraction and are discarded with the turn.
- Retrieval: when `.librarian/index/embeddings.sqlite` exists, `run_chat` builds a `Retriever`
  (`retrieval.state.retriever_for`, embedder from settings) and hands it to the `ToolContext`, so the
  model is offered `semantic_search` beside `search_documents`; rule 1 of the system prompt says to
  use it first for open questions, `search_documents` for exact terms, and to read with
  `get_document` before citing. The tool searches only the pages of the chat's readable catalog
  (`_readable`, then the localized view), so a withheld page is never a hit; `sources` still come from
  the `get_document` trail, never from search hits. Without an index the tool does not exist and the
  turn behaves as before. The question reaches the configured embedder (`KB_EMBED_URL`) when one is
  set; with the hash embedder it stays on the host.
- `SpendLedger`: day-keyed on UTC, written atomically (temp file + `os.replace`), a `threading.Lock`
  per ledger around every read-modify-write, re-read from disk on each call, days older than 31
  dropped on write; `add` rejects a negative or non-finite cost. An unreadable or malformed file is
  treated as empty and logged at WARNING.

## Residual risks and reviewer attention points

- Cost from an unauthenticated endpoint: bounded per turn by the ceilings, per client by the API
  throttle (10/min) and per day, all clients together, by `KB_CHAT_DAILY_BUDGET_USD` through the
  ledger. The action modes are one turn each, like a question.
- A corrupt ledger file resets the day's count to zero (logged), and a day total that is not a
  finite, non-negative number (JSON `NaN`/`Infinity` parse) is dropped the same way — it can never
  disable the ceiling; the per-turn cap still bounds each call. The lock is per process: several worker processes on one volume serialise through the
  atomic replace, not through the lock, so concurrent adds from different processes can lose a write.
- Withheld pages are removed from the chat's catalog (`_readable`) using the same per-page
  verdict the API uses (`Document.sensitive`), and that filter is installed as the
  `ToolContext.view` so a tool that reloads the catalog (`run_checks`) re-applies it — the model
  cannot list, search, read or paraphrase a page a reader may not open. Pages withheld only by a
  *finding of the latest audit* (not their current text) are not excluded here — the two sets
  coincide unless the page was edited since; the API's context check covers both sets.
- The quiz prompt asks for strict JSON; a model that answers in prose costs a turn and yields a 502.

## Reviewer checklist

- [ ] Only read tools are built; no `build_write_tools`/Atlassian factory in the chat runner.
- [ ] `_readable` is both the initial catalog and the `ToolContext.view` (survives `reload()`).
- [ ] Ceilings come from settings and cannot be raised by the request body, in any mode.
- [ ] Sources are derived from the trail, not from the model's text.
- [ ] The selection and context only ever reach the user prompt; the system prompt is a constant.
- [ ] `parse_quiz` rejects out-of-range answers and does not return a partial quiz.
- [ ] `SpendLedger.add` is only ever called with the SDK's reported cost; no caller can lower a total.

## Sign-off

Submit with `kb-librarian security submit chat`; the reviewer records the decision with
`kb-librarian security sign chat …`, which appends a row here and to `security/signoffs/chat.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
