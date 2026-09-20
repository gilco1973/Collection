# Walkthrough: mcp-tool-server

## 1. Run the live example

```
cd components/python/mcp-tool-server && python3 example.py
```

Two halves. In process: the handshake, `tools/list` with annotations (`readOnlyHint` true only for the read), a
read coming back projected, a W1 comment that parks and runs once after the elicitation is accepted, a W2 refused
without an approver. Over Streamable HTTP on localhost: the RFC 9728 metadata, a poisoned read that taints the
session, the next write answered 403 with `insufficient_scope, scope="tickets:write"`, and an elicitation sent on
the SSE stream and answered by a second POST.

## 2. Read the tests next to the rules

```
python3 -m unittest discover -s tests -t . -v
```

`tests/test_server.py` has one test per rule in the README: annotations from the catalog, declined means nothing
ran, taint and scope as typed errors, sampling disabled, the HTTP transport end to end.

## 3. Talk to it from a terminal over stdio

```
MCP_BEARER_TOKEN=$(python3 -c "import example; w=example.build(); print(w.token('u_dana'))") \
python3 -c "import example; from mcpserver import serve_stdio; serve_stdio(example.build().server)"
```

Then paste, one line each:

```
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}},"clientInfo":{"name":"me","version":"0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"tickets___comment","arguments":{"key":"T-1","body":"hello"}}}
```

The server answers the last one with an `elicitation/create` request; answer it with
`{"jsonrpc":"2.0","id":"srv_1","result":{"action":"accept","content":{"confirm":true}}}` and the call runs.
(The token above is issued by the example's fake identity provider for the example's own process; a real client
gets one from the identity provider.)

## 4. Copy it into your project

```
cp -r components/python/mcp-tool-server yourproject/mcp
```

Everything it imports is inside the directory (`actionloop/` is a vendored copy, declared in `component.json`).

## 5. Wire it

Replace `example.build()` with your harness: your catalog, your rules bundle, your handlers behind the gateway.
Keep `admit` small: board, ticket, budget, and the caller's bearer straight to the harness. Serve with
`serve_http(server, host, port, resource=<your resource URL>, authorization_servers=[<your idp>])`.

## 6. Prove it

Run the tests against your catalog; then, from Claude Code or any MCP client that supports elicitation, call a W1
tool and watch it ask before it runs. Run the official conformance suite when you have it and keep its
expected-failures file reviewed; that file is the replacement test's evidence.
