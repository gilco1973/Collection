---
title: Evaluating the librarian
owner: ai-platform-engineering
status: active
reviewed: 2026-09-18
tags: [governance, evaluation, agents]
audience: [engineer, leadership]
---
# Evaluating the librarian

The librarian's chat answers readers from these pages. Every change to its prompt, tools, model
or index gets a number before it is trusted: the golden set in `evals/golden.yaml` is run through
the real chat path and scored, nightly and on demand. This page says what is measured, what
"pass" means, how to add a question, and how to read a run.

## What is measured

Each item is one authored question with the pages a good answer cites (`expect.paths`), keywords
the answer must and must not contain, and whether the right answer is a refusal. The runner asks
the question through `run_chat` — the same gate, hooks and read-only tools a reader's question
goes through — and scores the answer without a second model call:

| Measure | Meaning |
| --- | --- |
| Citation precision | Of the pages the answer read and cited, the share that were expected |
| Citation recall | Of the expected pages, the share the answer cited |
| Keywords | Every `must_contain` present (case-insensitive) and no `must_not_contain` |
| Refusal correctness | The answer refused exactly when it should: no sources, and either a refusal phrase in English, Spanish or Hebrew, or at most two sentences |
| Cost and duration | What the turn was billed and how long it took |

An item whose turn errors scores zero on every measure but keeps what it cost. Items the budget
did not reach are `skipped` and do not count.

## Thresholds

`kb.config.yaml` `evals:` holds the pass marks; the command exits 1 when a run's average falls
below a rate or its total cost exceeds the ceiling:

| Threshold | Default |
| --- | --- |
| `citation_precision` | 0.8 |
| `citation_recall` | 0.7 |
| `refusal_correctness` | 1.0 |
| `max_cost_usd_per_run` | 5.0 USD |

Change them through the [review process](review-process.md) like any other rule in the contract.

## Running it

```bash
kb-librarian eval                       # the whole set, budget from kb.config.yaml
kb-librarian eval --items 10 --lang es  # a subset; --budget 1 caps the spend
kb-librarian eval --json                # the run as JSON (what the nightly job prints)
```

Exit 0 when every threshold passes, 1 when one is missed, 2 when the golden file is invalid or
every item errored (usually: no model credential — `kb-librarian doctor --model`). The run stops
before the next item would push the cumulative cost past the budget. Reports land in
`.librarian/evals/<date>.json` and `.md` on the state volume: the questions, the answers, the
cited paths and the scores — never a page body, never a reader's data.

The nightly job (`librarian-eval.yml`) runs only when the model credential is configured, with
its own `KB_MAX_BUDGET_USD` ceiling and without `KB_ALLOW_LIVE`; it posts the Markdown summary into
the job summary and keeps both reports as a 30-day artifact.

## Adding a golden item

1. Read the page the question should be answered from. Pick keywords that appear in it verbatim.
2. Append to `evals/golden.yaml` (`version: 1`) an item shaped like this:

   ```yaml
   - id: gov-review-change
     question: How does a change to a page get reviewed and merged?
     persona: engineer          # an audience value from kb.config.yaml
     lang: en                   # en, or one of i18n.languages
     expect:
       paths: [governance/review-process.md]
       must_contain: [kb-librarian check, owner]
       must_not_contain: []
       refuse: false
     tags: [governance, engineer]
   ```

3. For a topic the knowledge base does not cover, set `refuse: true` and list no paths. A page
   that is withheld (a sensitive hit) may only be the subject of a refuse item.
4. For Spanish or Hebrew, translate the question and keep the English paths; prefer identifiers
   and numbers as keywords, since the answer will be in that language.
5. `kb-librarian eval --items 1 --golden evals/golden.yaml` validates the file (ids unique, paths
   readable, persona and language known) before it spends anything.

## Reading a run

The Markdown report opens with the verdict and the four threshold rows, then one row per item.
A low precision with high recall means the answer read more pages than it needed; the reverse
means it missed the page that mattered — usually a search or wording problem, sometimes a page
that should be linked from its section landing page. A refusal miss on a `refuse: true` item
means the model answered from the wrong page: check whether a page really does cover the topic
and either fix the item or the page. Compare runs by their `golden_sha256`: a change in the set
explains a change in the numbers.
