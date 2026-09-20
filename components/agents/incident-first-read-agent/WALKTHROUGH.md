# Walkthrough: incident-first-read-agent

## 1. Run the live example

```
cd components/agents/incident-first-read-agent && python3 example.py
```

Six lines: the agent's name, ladder and tools by tier (all from `TEMPLATE.md`); the first read with its hypothesis
and cited claims; the advisory proposal; the parked W1 comment (nothing posted yet); the comment posted after one
confirmation; then the poisoned ticket, where the proposal is refused and the write is blocked; and the chain
verifying every record.

## 2. Read the template

Open `TEMPLATE.md`. The `json` block is the whole agent: change a tool's tier from `R` to `W1` and rerun the example;
the harness now parks that call too. Remove `propose` from `stages`; the comment says the agent does not propose.
Add a tool; `build()` signs it into the catalog and `tests/test_agent.py::test_the_catalog_is_built_from_the_template`
proves the catalog matches.

## 3. Run the tests, one per `never` line

```
python3 -m unittest discover -s tests -t . -v
```

Read `tests/test_agent.py` next to the `never` list: each line of the list has a test that would fail if the line
stopped being true. When you write your own agent, write the `never` list first and its tests second.

## 4. Copy it into your project

```
cp -r components/agents/incident-first-read-agent yourproject/agents/first-read
```

Everything it imports is inside the directory (`actionloop/`, `engine.py`, `guard.py` are vendored copies, declared
in `component.json`).

## 5. Wire it

In `example.py`, replace `FakeTickets` and `FakeDeploys` with clients for your systems: the same method names and
the `handler(args, credential)` shape, where `credential["on_behalf_of"]` is the acting person. Keep `build()`.
For a model behind the think step, construct `ModelEngine(complete, role=template["role"])` from `engine.py` with
`complete` from `bedrock-converse-adapter`, and pass it to `FirstReadAgent`.

## 6. Serve it over MCP

```
python3 example_mcp.py
```

The same `build()`; `McpToolServer` in front of it. `tools/list` is the template's three tools with annotations
from their tiers, and the W1 comment reaches the client as an elicitation. For a real client, `serve_http` from
`mcpserver/transports.py` puts it on Streamable HTTP; see `mcp-tool-server`.

## 7. Prove it

Rerun the tests, then run the example against your fakes with a poisoned ticket of your own. Sign the component
off on the hub when it has run once for real.
