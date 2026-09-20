# use-case-to-backlog

One plan file becomes a Jira-ready backlog: a Markdown file per epic and ticket, an index with totals and the critical path, and a CSV for Jira's importer. The specification's plan section renders from the same file, so the two never drift.

## Five-minute start

```
cd components/skills/use-case-to-backlog
python3 build_backlog.py example_plan.py out/    # 3 epics, 5 tickets, 27 points, the critical path
python3 -m unittest discover -s tests -t . -v
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure (also published in the knowledge base's skills catalog) |
| `build_backlog.py` | The builder: epic and ticket pages, README index, critical path, CSV |
| `example_plan.py` | The plan shape, five tickets |
| `tests/` | Builds the example and checks totals, links, checkboxes, CSV rows, the critical path |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The plan and backlog builder of the first responder's use case (28 tickets, 167 points), generalised.
