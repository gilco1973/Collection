---
title: "Audit chain"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [governance, observability, security]
audience: [engineer]
---
# audit-chain

> A component of the collection: `components/python/audit-chain/` in the repository (category tool, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.7 (PLT-AC-25, PLT-AC-26, PLT-AUD-1, PLT-AUD-3, PLT-AUD-12); the replacement test is under Known limits. Version 1.0.1; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


A hash-chained, append-only record in SQLite. One file, no dependencies. Every record carries the hash of the
previous one; `verify()` walks the chain and stops at the first broken link; `export()` writes JSON lines with the
chain head for the evidence a reviewer or an examiner asks for.

## What it is for

Anything a model or an agent did on your behalf needs a record that a later edit cannot quietly change: which tool,
which decision, on whose authority, with what result summary. A log line can be rewritten; a chained record cannot
without the verification failing. In Meg this is the incident record: the timeline in the room is a projection of it
and the postmortem is its export.

## Five-minute start

```python
import sqlite3
from audit import AuditChain

chain = AuditChain(sqlite3.connect("record.db"))
chain.record(consumer="agent:helper", event="decision", tool="tickets___comment", tier="W1", decision="allow", session="ses_1")
print(chain.head())              # sha256:...
print(chain.verify())            # number of records, or AuditError on the first broken link
chain.export("evidence.jsonl")   # {"records": n, "head": ..., "signed": False}
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `audit.py` | `AuditChain`: `record(**fields)`, `head()`, `verify()`, `query(**where)`, `export(path)`; `GENESIS`; `AuditError` |
| `tests/test_audit.py` | The head moves, tampering breaks the chain, queries by column and by body field, export |

## How to reuse it

Copy `audit.py`. Pass any fields: `consumer`, `env`, `event`, `tool`, `tier`, `decision` and `deny_code` become
indexed columns, everything else lives in the JSON body and is still queryable. Keep the record on a volume that
survives restarts; anchor the head with a signature from your key service on export when you have one.

## Rules it enforces

- Append only; `prev` and `hash` are computed on insert from the canonical body.
- `verify()` refuses any record whose `prev` is not the previous hash or whose hash does not match its body.
- The export is marked unsigned until a signer anchors it.

## Where it came from

Meg (`meg/crai/audit.py`, snapshot 2026-09-19), unchanged apart from docstrings. `governed-action-loop` vendors this
file.

## Known limits

One writer at a time (SQLite). The body is stored as JSON text; large payloads belong elsewhere with a reference here.

**Replacement test** (the platform specification's §14.3 rule for an interim): The same records verify under the platform's audit trail and the export head is anchored by a KMS signature; a chain written here imports without a broken link.
