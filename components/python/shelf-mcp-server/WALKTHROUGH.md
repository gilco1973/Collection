# Walkthrough: shelf-mcp-server

## 1. Run the live example

```
cd components/python/shelf-mcp-server && python3 example.py
```

The server starts as a subprocess; the example initializes, lists the tools (all read-only), lists the agents,
searches for "mcp", gets one component with its sign-offs, reads its README as a resource, and asks for a
`shelf_sign` tool that does not exist.

## 2. Register it with Claude Code

```
cd <the collection> && claude mcp add shelf -- python3 components/python/shelf-mcp-server/server.py --root .
```

Ask: "What is on the shelf for verifying a JWT, and how do I use it?" The assistant calls `shelf_search`, then
`shelf_get`, then reads `shelf://rs256-jwt-verify/README.md`.

## 3. Run the tests

```
python3 -m unittest discover -s tests -t . -v
```

## 4. Copy it

```
cp -r components/python/shelf-mcp-server yourproject/shelf-mcp
```

`protocol.py` is a vendored copy, declared in `component.json`.

## 5. Wire it

Point `--root` at the checkout your team uses. To serve it over HTTP to many assistants, wrap its four tools as a
read-only catalog behind `mcp-tool-server`.

## 6. Prove it

From your assistant, ask for a component and copy it from the path the answer gives; run its test command. Sign
this component off on the hub when it has been used once for real.
