# runbook-answerer

The AI Playground's sample candidate: a small pattern that answers a question from one runbook extract. It is here
so the playground's five-minute start ends on a real component and a clear report; copy its shape, not its rules.

## What it is for

Answering an operator's question from the runbook extract a search step found, with the extract named, and
nothing that the extract's author slipped into it.

## Five-minute start

```sh
python3 example.py
python3 -m unittest discover -s tests -t .
```

## What is inside

- `answerer.py`: `answer(prompt, context)` returns `{"output", "citations"}`.
- `example.py`: the live example.
- `tests/`: one test per rule below.

## How to reuse it

Copy `answerer.py`; call `answer` with the question and the extract your retrieval step returned.

## Rules it enforces

- Lines of the extract that read as instructions to an assistant are dropped before it is read.
- Secret-shaped settings and card or national-id numbers are masked.
- Instructions in the question and money movement are refused.
- An answer names its extract; a question the extract does not cover is said to be uncovered.

## Where it came from

Written for the AI Playground's examples; nothing was lifted from a product.

## Known limits

Keyword matching, not a model: it finds lines that share a word with the question. The instruction filter is a
list of phrases, so a new phrasing gets through; the playground's probes are how you find out.
