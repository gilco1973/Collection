---
title: "Mcp gateway client"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, governance]
audience: [engineer]
---
# mcp-gateway-client

> A component of the collection: `components/python/mcp-gateway-client/` in the repository (category integration, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.12, §5.2, §4.1 (PLT-CAT-7, PLT-CAT-10, PLT-CAT-6, PLT-AC-16, PLT-ID-6); the replacement test is under Known limits. Version 1.0.1; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


The harness's gateway for an external MCP server: a recorded contract, an allowlist pinned to descriptions, quarantine on drift, credentials by name; a fake.

## What it is for

When an agent's tools live on an MCP server someone else runs, the specification treats that server as a system
of record: it enters the contract registry with a verified publisher and a key fingerprint, the consumer gets a
signed allowlist of the tools it may call, and any change to a tool's description quarantines the server until a
person re-verifies (PLT-CAT-7, PLT-CAT-10). This is that gateway, standard library only, behind the same
`tools_list` and `tools_call` the harness already calls on its fake gateway. The harness decides; the gateway
carries the call over MCP and nothing more.

## Five-minute start

```
cd components/python/mcp-gateway-client
python3 example.py
python3 -m unittest discover -s tests -t .
```

The example pins a contract from a reviewed `tools/list`, runs a read and a confirmed W1 through the harness
over the fake server, shows a tool that is on the server but not on the allowlist refused before any call, and
then changes a description upstream: the gateway quarantines, and the next call is a typed stop.

## What is inside

| File | What it is |
| --- | --- |
| `mcpgateway/contract.py` | `Contract`: server, publisher, fingerprint, `allow` (harness name to remote tool and the sha256 of its description as reviewed); `record()` from a reviewed tools/list, `verify()` returns the problems that quarantine; descriptions scored for injection |
| `mcpgateway/client.py` | `McpGateway` (`verify`, `tools_list`, `tools_call`, `release`), `HttpTransport` (Streamable HTTP with the bearer looked up by name at call time), `FakeMcpServer` (in memory, same `rpc` surface, a `forbid` set) |
| `mcpgateway/protocol.py` | JSON-RPC framing, vendored from `mcp-tool-server` |
| `example.py` | `build()` wires the harness with the gateway in the fake gateway's place |
| `tests/test_gateway.py` | The contract rules, the harness through the gateway, remote forbidden and error results, quarantine and release, the credential by name, the HTTP transport against a stub |
| `actionloop/` | The harness, vendored verbatim from `governed-action-loop` |

## How to reuse it

Copy the directory. Review the server's `tools/list` once, with the security engineer, and pin it:

```python
contract = Contract.record("tickets-mcp", publisher, fingerprint, tools, {"tickets___get": "get_ticket"})
gateway = McpGateway("tickets-mcp", contract, HttpTransport("https://<the server>/mcp"), token_env="TICKETS_MCP_TOKEN")
harness = Harness(..., gateway=gateway, ...)
```

Store `contract.to_json()` with the consumer and load it with `Contract.from_json`; a new allowlist is a new
contract version, reviewed again. The publisher and fingerprint come from the registry's verification of the
server (a registry proof or a DNS or HTTP challenge); the fake carries them in `serverInfo` so the example can run.

## Rules it enforces

- Only tools on the signed allowlist are listed to the harness or callable; a tool the server offers but the contract does not is refused at the catalog hook, before any call.
- A changed description, publisher or key fingerprint quarantines the server: every call is a typed stop until a person releases it, and the release is on the gateway's log with their name.
- Tool descriptions are corpus payload locations: one that scores as an injection quarantines even when it was reviewed.
- The harness's hooks run first; a parked W1 never crosses the wire, and a remote forbidden answer is a deny with a typed code.
- The credential for the server is an environment variable name resolved at call time; nothing here holds one.

## Where it came from

The gateway shape is `meg-first-responder`'s `meg/crai/gateway.py` (the fake gateway the harness ships with).
The contract record, the quarantine and the description scoring are new, written to the platform design
specification §4.12. The transport is the client half of `mcp-tool-server`.

## Known limits

No elicitation on this side by design: the person confirmed with the harness already, so a server that asks for
a confirmation of its own is answered "declined". The registry verification of a publisher (proof, challenge) is
the registry's; this component takes the result. No resumable HTTP stream.

**Replacement test:** the same contract record lives in the platform's contract registry and the same allowlist is
the Gateway target's; a changed description, publisher or fingerprint quarantines the target there exactly as
here, and the harness's conformance tests through the gateway pass on both.
