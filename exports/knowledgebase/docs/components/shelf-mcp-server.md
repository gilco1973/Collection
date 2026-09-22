---
title: "Shelf mcp server"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [agents, paved-road, skill]
audience: [engineer]
---
# shelf-mcp-server

> A component of the collection: `components/python/shelf-mcp-server/` in the repository (category tool, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §7.4, §4.11 (PLT-CAT-5, PLT-HAR-33); the replacement test is under Known limits. Version 1.0.2; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


A read-only MCP server over the shelf: list, get, search and stage tools and every README, walkthrough and
template as resources, for a coding assistant.

## What it is for

A coding assistant working in a champion's project should be able to ask "what is on the shelf for this, and how
do I use it" without cloning the collection. This server answers from the manifests: which components exist, by
category; a component's version, both sign-offs and stage; a word search; and every README, walkthrough,
template and SKILL.md as a resource. It never runs, writes or signs anything: the manifest stays the record, the
hub and the shelf tool do the writing.

## Five-minute start

```
cd components/python/shelf-mcp-server
python3 example.py                                    # drives the server as a subprocess over stdio
python3 -m unittest discover -s tests -t .
```

For Claude Code, from the repository root:

```
claude mcp add shelf -- python3 components/python/shelf-mcp-server/server.py --root .
```

Then ask it what is on the shelf for, say, verifying a JWT; it lists `rs256-jwt-verify`, reads its README as a
resource, and tells you the copy command and the test command.

## What is inside

| File | What it is |
| --- | --- |
| `server.py` | `Shelf` (reads every `component.json` under `components/`), `ShelfServer` (initialize, tools/list, tools/call, resources/list, resources/read, ping), `serve_stdio`, `stage_of` (the shelf tool's rule) |
| `protocol.py` | JSON-RPC framing, vendored from `mcp-tool-server` |
| `example.py` | The walk-through over stdio: list agents, search, get, read a README, try a write tool and be refused |
| `tests/test_shelf.py` | Complete listing by category, get and search, resources limited to component files (no path escape), no write tools, the stage rule, the stdio loop |

## How to reuse it

Copy the directory anywhere; point `--root` at a checkout of the collection (or at any tree of `component.json`
manifests in the same contract). Register it with your assistant as above. To serve it to a team over HTTP, put it
behind `mcp-tool-server`'s transport with a read-only catalog; the tools here are all `readOnlyHint`.

## Rules it enforces

- Every tool is read-only and idempotent and says so in its annotations; there is no tool that runs, writes or signs, and the tests try three.
- Resources are exactly the component files (`README.md`, `WALKTHROUGH.md`, `TEMPLATE.md`, `SKILL.md`, `component.json`); a URI cannot reach anything else.
- The stage and sign-off state are read from the manifest with the shelf tool's rule; nothing is inferred.

## Where it came from

Written for the collection; the stage rule mirrors `tools/shelf.py`, and the tests keep the two in step.

## Known limits

The stage rule is duplicated from the shelf tool (a component imports nothing outside its directory); a change to
the rule is made in both places. Stdio only; no search index beyond word matching.

**Replacement test:** the platform's registry exposes the same records over its own MCP endpoint (§4.11: one
discoverable record per component with version and owner); a coding assistant configured against either gets the
same list, the same stage and the same pages.
