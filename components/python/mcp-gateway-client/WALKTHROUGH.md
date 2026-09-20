# Walkthrough: mcp-gateway-client

## 1. Run the live example

```
cd components/python/mcp-gateway-client && python3 example.py
```

Eight lines: the contract's allowlist, a read carried over MCP, the W1 parked by the harness before any wire
call, the same W1 after confirmation, a tool on the server but not on the allowlist refused, a description changed
upstream and the two problems `verify()` reports (changed, and scoring as an injection), the quarantined server
answering with a typed stop, and the chain verifying.

## 2. Read the contract

Open `mcpgateway/contract.py`. `record()` is what a review produces: for each harness tool name, the remote tool
and the hash of its description as it was read. `verify()` is what runs at start and whenever you call it: the
list of reasons the server is not what was reviewed. Change a description in `example.REMOTE_TOOLS` and rerun.

## 3. Run the tests, one per rule

```
python3 -m unittest discover -s tests -t . -v
```

## 4. Copy it into your project

```
cp -r components/python/mcp-gateway-client yourproject/gateway
```

Everything it imports is inside the directory (`actionloop/` and `mcpgateway/protocol.py` are vendored copies).

## 5. Wire it

Point `HttpTransport` at the server, name the environment variable that holds the token for it, pin the contract
with the security engineer, and pass the gateway to your `Harness` in place of the fake. Keep the contract JSON
next to the consumer's catalog; bump its version when the allowlist changes.

## 6. Prove it

Run the tests; then change one description on the real server in a sandbox and watch `verify()` quarantine it.
Sign the component off on the hub when it has run once for real.
