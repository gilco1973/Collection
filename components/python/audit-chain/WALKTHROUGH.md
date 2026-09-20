# Walkthrough: audit-chain

## 1. Run the live example

```
cd components/python/audit-chain && python3 example.py
```

Three records, a head hash, a verification count, an export marked unsigned, then a tampered record and the verification failing on it.

## 2. Copy the file

```
cp audit.py /path/to/your-service/
```

One file, standard library. Open a SQLite connection on a volume that survives restarts and pass it to `AuditChain`.

## 3. Record what matters

Call `record(**fields)` at every decision point: admission, each decision with the policy ids, the intent of a write before it runs, confirmations with their hash, stops with their typed reason, model calls with their context. `consumer`, `env`, `event`, `tool`, `tier`, `decision` and `deny_code` become indexed columns; everything else is in the body and still queryable.

## 4. Project, never copy

Render what people see (a timeline, a console page) from `query(...)`, and verify the projection against the chain before showing it. Nothing appears that is not on the record.

## 5. Export for reviewers

`export(path)` writes JSON lines and returns the head. Attach the head to the postmortem or the evidence bundle. Until a key service signs the head, the export says `signed: false`; the readiness page should say so too.

## 6. Prove it

```
python3 -m unittest discover -s tests -t . -v
```

Four tests: the head moves, tampering breaks the chain, queries, export.
