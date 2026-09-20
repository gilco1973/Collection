---
title: "Bedrock converse adapter"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, cost]
audience: [engineer]
---
# bedrock-converse-adapter

> A component of the collection: `components/python/bedrock-converse-adapter/` in the repository (category integration, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.8 (PLT-AC-29, PLT-AC-30, PLT-MDL-1, PLT-MDL-2); the replacement test is under Known limits. Version 1.0.0; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


Claude on Amazon Bedrock Converse behind the one signature the model gateway calls:
`complete(model_id, system, user, max_tokens) -> (text, input_tokens, output_tokens)`. Signed with SigV4 from the
task role, so there is no API key anywhere; an application inference profile ARN travels as the `modelId`; token usage
comes back for the session budget; a Bedrock Guardrail can be attached as a second signal.

## Five-minute start

```python
from bedrock import BedrockConverseAdapter
from httpclient import Http                                   # stdlib-http-client
adapter = BedrockConverseAdapter(Http(), region="us-east-1")   # credentials from the task role
text, tin, tout = adapter.complete("arn:aws:bedrock:...:application-inference-profile/...", system_prompt, user_text, 2000)
```

With `governed-action-loop`: `ModelGateway(adapter, profiles, allowlist, prompts, telemetry)` replaces `FakeModel`
and nothing above the gateway changes.

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `bedrock.py` | `BedrockConverseAdapter(http, region, endpoint, anthropic_version, guardrail_id, guardrail_version, creds_loader)`, `BedrockConverseError` |
| `sigv4.py` | Vendored from `aws-sigv4` |
| `tests/test_bedrock.py` | Request shape (URL, headers, body, guardrail), usage parsing, refusal on an unusable response, a custom endpoint |

## Rules it enforces

No secret in code or configuration: ARNs and names only. An answer without a usable message is an error the caller
turns into a typed stop (`vendor.refusal`), never a guess.

## Where it came from

Meg (`meg/responder/clients/bedrock.py`, snapshot 2026-09-19).

## Known limits

Converse only, no streaming. The Guardrail is a second signal; keep the taint ceiling as the control.

**Replacement test** (the platform specification's §14.3 rule for an interim): The model gateway service calls Converse with the same inference profile; this adapter is retired when the gateway serves the same `complete` contract.
