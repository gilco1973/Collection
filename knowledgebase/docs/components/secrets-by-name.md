---
title: "Secrets by name"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [security]
audience: [engineer]
---
# secrets-by-name

> A component of the collection: `components/python/secrets-by-name/` in the repository (kind tool, python, status ready). Copy it from there; this page is its README, published by the catalog tool.


A handler never holds a credential. It asks a provider for a *named* secret at call time; the provider is AWS
Secrets Manager in production, a JSON file in a sandbox, or the environment in tests. Values are cached briefly and
never logged. `require_credential` is the other half: a handler refuses to run unless the loop redeemed a reference
for its own audience on this call.

## Five-minute start

```python
import secrets as S
provider = S.provider_from_env(prefix="APP_")            # APP_SECRETS=env|file:/path.json|aws
key = provider.get("pagerduty/api")                      # APP_SECRET_PAGERDUTY_API in env mode

def acknowledge(args, credential):                       # a gateway handler
    who = S.require_credential(credential, "pagerduty")  # refuses without a redeemed reference
    ...
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `secrets.py` | `EnvSecrets`, `FileSecrets`, `DictSecrets`, `SecretsManager` (over `aws-sigv4`'s `AwsJson`, five-minute cache), `provider_from_env`, `require_credential`, `UpstreamError` |
| `tests/test_secrets.py` | The three providers, the cache, the selector, the credential check |

## How to reuse it

Copy `secrets.py`. Configuration carries secret *names* (`app/pagerduty-api`); rotation is a change in the vault and
nothing restarts. Give every client the provider and the name; fetch inside the call.

## Where it came from

Meg (`meg/responder/secrets.py` and `clients/__init__.py`, snapshot 2026-09-19), with the environment prefix made a
parameter.

## Known limits

`SecretsManager` needs an object with `call(service, prefix, target, payload)` (see `aws-sigv4`). Other vaults are a
class with one `get` method.
