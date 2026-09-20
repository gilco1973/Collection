---
title: "Mcp tool server"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, governance]
audience: [engineer]
---
# mcp-tool-server

> A component of the collection: `components/python/mcp-tool-server/` in the repository (category harness, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §7.4, §4.12, §4.1, §5.1 (PLT-CAT-5, PLT-CAT-6, PLT-HAR-33, PLT-ID-6, PLT-AC-11, PLT-AC-16, PLT-AC-21); the replacement test is under Known limits. Version 1.0.0; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


An MCP server in front of the action loop: tools/list from the signed catalog with annotations, every call through the hooks, W1 as elicitation, taint as 403.

## What it is for

The platform's R1 road is "an MCP server: tools exposed to an AI client that holds the model, with the harness
behind the transport". This is that shape, standard library only: JSON-RPC 2.0 over stdio or Streamable HTTP in
front of the same `Harness` the agents use. The protocol is the wire and nothing more. Tiers, taint, budgets,
kill switches and the chained record stay in the harness, where a client cannot reach around them: a W1 call parks
and is put to the person as an elicitation, a tainted or out-of-scope call is a typed forbidden error the HTTP
transport answers with 403 and `WWW-Authenticate: insufficient_scope` naming the scope, and sampling is disabled.
Reach for it when a champion's tool set should be callable by Claude Code, the hub's assistant or a partner client
the same way, with the same controls.

## Five-minute start

```
cd components/python/mcp-tool-server
python3 example.py                                   # in process, then over Streamable HTTP on localhost
python3 -m unittest discover -s tests -t .
```

The example prints the handshake, the three tools with their annotations, a read coming back projected, the W1
comment running once after the person accepts the elicitation, a W2 refused without an approver; then the same
over HTTP: the protected-resource metadata, a poisoned read tainting the session, the next write answered 403
with the scope, and an elicitation carried on the SSE stream and answered on a second POST.

## What is inside

| File | What it is |
| --- | --- |
| `mcpserver/protocol.py` | JSON-RPC 2.0 framing, the standard error codes and three of this server's: forbidden, confirmation declined, stopped |
| `mcpserver/server.py` | `McpToolServer`: initialize (admits with the bearer), tools/list (the catalog as MCP tools; annotations from tier, reversibility, idempotency, egress), tools/call (through the hooks; elicitation for W1), sampling refused |
| `mcpserver/transports.py` | `InProcessClient` (tests, examples), `serve_stdio` (newline JSON-RPC; the bearer read from a named environment variable), `serve_http` (Streamable HTTP: sessions, SSE for server-to-client requests, 401 and 403 with `WWW-Authenticate`, RFC 9728 metadata) |
| `example.py` | `build()` wires a three-tool catalog behind the harness; `HttpClient` is a small client enough for the walk-through |
| `tests/test_server.py` | The handshake, annotations from the catalog, reads through the hooks, W1 only after accept, declined means nothing ran, taint and scope as typed errors, sampling disabled, and the HTTP transport end to end |
| `actionloop/` | The harness, vendored verbatim from `governed-action-loop` |

## How to reuse it

Copy the directory. Build your harness as `example.build()` does (your catalog, rules, handlers), then:

```python
server = McpToolServer(harness, admit, name="my-tools", version="1.0.0")   # admit(token) -> harness.admit(...)
serve_stdio(server, token_env="MCP_BEARER_TOKEN")                           # or
httpd = serve_http(server, host="<bind address>", port=8080, resource="https://<your host>/mcp", authorization_servers=["https://<your idp>"])
```

`admit` is yours: it chooses the board, the ticket and the budget for a session and hands the caller's bearer to
the harness, which resolves it through the identity library. The server never sees a credential of its own. Tool
names are the harness's (`target___op`), so the catalog, the policy bundle and the MCP surface stay one thing.

## Rules it enforces

- Every tools/call runs the harness's three hooks; there is no method that reaches a handler around them.
- tools/list is rendered from the signed catalog; annotations are derived from it and never read from a client.
- A W1 call runs only after the person accepts the elicitation for the exact tool and arguments; a client without the elicitation capability, a decline, a cancel or a timeout means nothing ran.
- A deny for taint, ladder, scope or a kill switch is a typed forbidden error; over HTTP it is 403 with `WWW-Authenticate: Bearer error="insufficient_scope", scope=<permission>`.
- A request without a bearer is 401 with the protected-resource metadata location; sampling is never offered and `sampling/*` is method-not-found.
- Every call, decision, confirmation and stop is on the chain, whatever the transport.

## Where it came from

The loop is `meg-first-responder`'s `meg/crai`, vendored from `governed-action-loop`. The transport is new,
written to the platform design specification §7.4 (R1 · MCP server) and the catalog rules of §4.12. Nothing was
lifted from a product's MCP server: the knowledge base's librarian runs an in-process one behind an agent SDK, and
that shape belongs to the product.

## Known limits

Elicitation is the only server-to-client request; there are no resources or prompts on this server (the shelf's
read-only server has resources). Streamable HTTP here has no resumable event store: a client that drops the stream
during an elicitation must ask again. Session state is in memory; the harness's session store is the durable one.

**Replacement test:** the same catalog and handlers run behind the platform's `crai.transport.mcp` on AgentCore
Runtime with the Redis event store; the official MCP conformance suite passes with the same reviewed
expected-failures file, and the W1 elicitation, the 403 insufficient_scope answer and the chain records are
identical on both.
