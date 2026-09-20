---
title: Fail closed, secrets by name, ids-only logs
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [best-practice, security, observability]
audience: [engineer]
---
# Fail closed, secrets by name, ids-only logs

Three small habits that remove whole classes of incident. Each is one file in the collection.

## Fail closed

A live process with a missing gate never starts. Configuration comes from the environment; an empty value means
unset, never "an empty gate that lets everyone through". `validate()` returns every problem at once, naming the
variable and never its value; the entrypoint runs `check-config` first and refuses to listen on exit 2. Fake mode
is refused in production. A memory store is refused in live mode because the record must survive a restart. A
public URL must be https.

The reviewer's test: set one gate to empty and start the container; it must not listen.

## Secrets by name

A handler never holds a credential. Configuration carries the *name* of a secret; the client fetches the value at
call time from the vault (a file in a sandbox, the environment in tests) and caches it briefly. Rotation is a change
in the vault and nothing restarts. Cloud calls are signed from the task role; no key exists to leak.

The other half is the redeemed reference: the loop mints a short-lived reference bound to the target audience and the
run, and the handler refuses to run without one for its own audience. A target holds no standing credential.

## Ids-only logs

No free text reaches a log line: not a ticket body, not a question, not an answer, not a log line from upstream.
The logger lets identifiers through (incident, session, turn, tool, stop reason), withholds long strings with a
count, masks anything that looks like a secret or an email, and caps lists. The chained record is the record; logs
carry ids so a person can find the record. The test suite seeds a distinctive text into the system and asserts it is
absent from the captured log stream.

If you see incident text in a log line, that is a security incident, by construction.

## Diagnostics without values

A `doctor` or start-up diagnostic prints presence and shape only: "set", "unset", "set (3 items)". Never a value,
never a length that identifies a value.

## Where it is implemented

`fail-closed-config`, `secrets-by-name` (with `require_credential`), `aws-sigv4` and `ids-only-logging` in the
collection. The knowledge base's own settings and logging follow the same rules; see the librarian's
[runbook practice](../paved-roads/use-case-001-knowledge-base.md).
