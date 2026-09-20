# Security review sheet: Librarian evaluation (golden set, scorer, `eval` command)

| | |
| --- | --- |
| Module id | `evals` |
| Kind | backend |
| Code | `kb_librarian/evals/` (`items.py`, `refusals.py`, `score.py`, `runner.py`, `report.py`), `kb_librarian/cli_evals.py`, `evals/golden.yaml` |
| Tests | `tests/test_evals_items.py`, `tests/test_evals_score.py`, `tests/test_evals_runner.py`, `tests/test_evals_cli.py`, `tests/evals_helpers.py` |
| Depends on | `chat/` (`run_chat`), `catalog/`, `kbconfig` (`evals:` thresholds), claude-agent-sdk (the real run only) |

## Purpose

Gives every change to the chat's prompt, tools, model or index a number. `evals/golden.yaml`
holds authored questions with the pages a good answer cites, keyword expectations and whether a
refusal is the right answer. `kb-librarian eval [--items N] [--budget USD] [--json] [--lang xx]
[--golden PATH]` runs each item through `run_chat` (the reader's path: gate, hooks, read-only
tools, readable-only catalog), scores citation precision/recall, keywords and refusal correctness
offline (no judge model), and writes `.librarian/evals/<date>.json` and `.md`.

## Entry points

`load_golden(path, root)`, `is_refusal(answer, lang, sources=)`, `score_item`, `summarise`,
`run_eval(settings, root, items, budget_usd=, lang=, query_fn=, out=, golden_path=, today=)`,
`write_reports`; CLI `add_evals_parser` / `cmd_eval` (exit 0 pass, 1 a threshold missed, 2 the
golden file is invalid, no item matched, or every item errored). Workflow `librarian-eval.yml`
(see the `deploy` sheet).

## Trust boundaries

Runs as the invoking user (CLI) or the CI job. The questions are authored and committed, not
readers' input; they reach the model through `run_chat` exactly as a reader's question would. The
golden file is validated before any turn runs: ids unique, every expected path a page in the
catalog that is **not withheld** (a withheld page may only be the subject of a `refuse: true`
item, which lists no paths), `lang` configured, `persona` an audience value.

## Data handled

On the state volume, `.librarian/evals/<date>.{json,md}`: the golden questions, the model's
answers, the cited paths, per-item scores, cost and duration, the golden file's SHA-256 and the
model/effort used. Never a page body (only paths), never reader data (no profile, session or
chat-log input). The CI artifact carries the same two files for 30 days. Progress lines and the
table print ids and numbers, never an answer.

## Secrets

None read directly. The real run needs the model credential the SDK reads from the environment;
the workflow gates every step on `secrets.ANTHROPIC_API_KEY` being present, like `live-smoke.yml`.

## External calls

The model API, only through `run_chat` (one capped turn per item). Unit tests inject a fake
`query_fn` and make no network call.

## Mutations

None to pages: the chat runner offers no write tool, and the evaluator adds none. Writes only its
own reports under `.librarian/evals/`. `KB_ALLOW_LIVE` is neither read nor set anywhere in the
module or the workflow.

## Controls in place

- Cost ceiling: `--budget` (default `evals.max_cost_usd_per_run` from `kb.config.yaml`); the run
  is sequential and stops before the next item would push the cumulative cost past the budget
  (estimate: the dearest turn so far); the rest are `skipped`. The per-turn chat cap
  (`KB_CHAT_MAX_BUDGET_USD`) bounds any one item. The workflow sets `KB_MAX_BUDGET_USD=5` and passes
  it as `--budget`.
- Withheld pages cannot be expected citations (validation error), and the chat's readable-only
  catalog means they cannot be read or cited during a run either.
- An erroring item is recorded (`error`: the runner's message, or the exception type alone when a
  turn raised), never raised; "every item errored" is exit 2 with a line naming the credential probe.
- Thresholds are in the contract, reviewed with the content; the `--judge` (second model call)
  option is out of scope and not implemented.

## Residual risks and reviewer attention points

- The answers written to the reports come from the model reading Internal pages; the reports
  are Internal tier like the pages and stay on the state volume / in the CI artifact.
- Refusal detection is heuristic (phrase list plus "no sources and ≤ 2 sentences"): a terse real
  answer with no page read counts as a refusal. That errs towards flagging, never towards hiding.
- Budget accounting relies on `ResultMessage.total_cost_usd`; a turn with no cost reported adds
  nothing to the running total.

## Reviewer checklist

- [ ] `load_golden` rejects a withheld path and a refuse item with paths.
- [ ] Reports contain paths, questions, answers and numbers only — no page body.
- [ ] `librarian-eval.yml` sets no `KB_ALLOW_LIVE`, gates on the secret, `contents: read`.
- [ ] The budget stop marks unreached items `skipped` and the summary excludes them.

## Sign-off

Submit with `kb-librarian security submit evals`; the reviewer records the decision with
`kb-librarian security sign evals …`, which appends a row here and to `security/signoffs/evals.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
