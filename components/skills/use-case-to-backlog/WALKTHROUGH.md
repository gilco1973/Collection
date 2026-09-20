# Walkthrough: use-case-to-backlog

## 1. Run the live example

```
cd components/skills/use-case-to-backlog
python3 build_backlog.py example_plan.py /tmp/backlog-example && cat /tmp/backlog-example/README.md
```

Ten files from a five-ticket plan: the index with totals, the by-phase table, all tickets, the critical path, the owner codes; one page per epic and ticket; a CSV for the importer.

## 2. Copy the plan shape next to your specification

```
cp build_backlog.py example_plan.py /path/to/your-usecase/build/
mv /path/to/your-usecase/build/example_plan.py /path/to/your-usecase/build/plan.py
```

## 3. Fill the plan

`PHASES` (the increments with weeks), `OWNERS` (role codes), `EPICS`, and one `t(...)` per ticket: key, type, epic, phase, weeks, owner, points, priority, dependencies, summary, description, acceptance criteria as a list, references. Keys are placeholders until the project exists.

## 4. Build and read the critical path

```
python3 build_backlog.py plan.py jira/
```

If the critical path does not end at the last increment's demonstration, the dependencies are wrong; fix the plan.

## 5. Import and commit together

Import `jira/jira-import.csv`; commit `plan.py` and `jira/` in the same change so the specification's plan section, the pages and Jira never drift.

## 6. Prove the builder

```
python3 -m unittest discover -s tests -t . -v
```
