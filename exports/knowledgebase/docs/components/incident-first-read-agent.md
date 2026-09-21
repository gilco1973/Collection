---
title: "Incident first read agent"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, governance]
audience: [engineer]
---
# incident-first-read-agent

> A component of the collection: `components/agents/incident-first-read-agent/` in the repository (category agent, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §5.1, §5.2, §5.5, §4.8, §4.5 (PLT-AC-8, PLT-AC-11, PLT-AC-16, PLT-AC-21, PLT-HAR-11, PLT-MDL-1, PLT-PRM-1, PLT-DATA-3); the replacement test is under Known limits. Version 1.0.2; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


An agent, complete: a template (role, stages, tools by tier, what it never does), tools called only through the
harness, a cited first read of an incident, one W1 proposal a person confirms.

## What it is for

The first thing a responder wants when an alert fires is a first read: what changed, what is failing, the leading
hypothesis, with every claim pointing at a source, and at most one proposed action they can confirm or ignore. This
is that agent, small enough to read in ten minutes, and the reference for what an agent in the collection is: a
template that says what it is and may call, tools it reaches only through the harness, and a harness
that enforces tiers, taint, budgets and the record. Copy it to start your own agent; replace the template and the
fakes, keep the loop.

## Five-minute start

```
cd components/agents/incident-first-read-agent
python3 example.py                                   # a clean incident, then a poisoned one; the chain verifies
python3 example_mcp.py                               # the same template served over MCP; the W1 comment is an elicitation
python3 -m unittest discover -s tests -t .           # one test per line of the template's "never"
```

The example prints the first read (hypothesis, cited claims), the advisory proposal, the parked W1 comment, the
comment posted after one confirmation, and then the poisoned ticket: proposal refused, write blocked, taint on
the record.

## What is inside

| File | What it is |
| --- | --- |
| `TEMPLATE.md` | The agent as data: name, role, ladder, road, channel, stages, budget, `tools` (target, op, tier, contract, permission, args, result shape) and `never` |
| `agent.py` | `load_template()`, `catalog_from(template)` (the signed catalog built from `tools`), `FirstReadAgent.run()` (read, think, propose, park the write) and `post()` (confirm once, then write) |
| `example.py` | `build()` wires the harness from the template with fake ticket and deploy targets; `main()` runs both scenarios |
| `example_mcp.py` | The same harness served over MCP: tools/list is the template's tools with annotations, the W1 comment is an elicitation |
| `tests/test_agent.py` | The happy path, and one test per `never` line: no write without a person, one confirmation for the exact call, refused on taint, nothing outside the template, only projected and masked text reaches the model, the chain verifies |
| `actionloop/` | The harness, vendored verbatim from `governed-action-loop` |
| `engine.py`, `guard.py` | The think step, vendored verbatim from `cited-llm-engine` |
| `mcpserver/` | The MCP transport, vendored verbatim from `mcp-tool-server` |

## How to reuse it

Copy the directory. Edit `TEMPLATE.md` first: the role sentence, the stages, the tools with their tiers and result
shapes, the `never` list. Then replace the two fakes in `example.py` with clients for your ticket system and your
deploy pipeline (same method shapes, `handler(args, credential)`; the `jira-connector` and `ado-connector` components are those clients, with the field names the template's result shapes expect), keep `build()` as it is, and write one test per
`never` line before you write anything else. The rules bundle in `example.py` is yours to change; the harness's
hooks are not. To use a model instead of the rules engine, hand `ModelEngine(complete, role=template["role"])` to
`FirstReadAgent`; `complete` is any `(system, user) -> text` callable, for example the `bedrock-converse-adapter`.

## Rules it enforces

- The catalog the harness loads is built and signed from the template's `tools`; a call to anything else fails at the catalog hook.
- A write (W1) parks with a hash of the exact tool and arguments; only the acting person confirms; the confirmation is consumed once.
- A proposal is refused before any model call when the context is tainted, and the harness caps a tainted session at reads.
- The model sees projected, masked, fenced sources only; claims without a citation are dropped; a malformed answer is refused.
- Every read, intent, decision, confirmation and stop is on the chain; `verify()` walks it.

## Where it came from

`meg-first-responder`, snapshot 2026-09-19: the first read of `meg/responder` (think step and its stages) on the
loop of `meg/crai`. Extraction: the template became a file the code loads rather than constants spread over
modules; the incident room, the connectors and the game day stayed in the product; the fakes are new. The
harness and the think step are vendored from their own components so this directory copies whole.

## Known limits

One agent, one turn: no room, no follow-up questions, no scan-and-fix stage. The rules engine is the default
engine; a model needs a `complete` callable and a prompt registry entry per stage.

Over MCP (`example_mcp.py`) the agent is the R1 shape: the client holds the model and calls the template's tools;
the harness is the same object, so the W1 comment is an elicitation and a tainted session is 403.

**Replacement test:** the same `TEMPLATE.md` runs unchanged with the platform's harness (AgentCore Runtime with
the three hooks, the catalog it declares signed into AgentCore Gateway, the stage prompts in the prompt registry);
the conformance tests on the first read, the refused proposal on taint and the once-confirmed W1 comment pass on
both.
