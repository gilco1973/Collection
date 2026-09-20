---
title: "RS256 jwt verify"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [security]
audience: [engineer]
---
# rs256-jwt-verify

> A component of the collection: `components/python/rs256-jwt-verify/` in the repository (category tool, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.1 (PLT-AC-14, PLT-ID-1, PLT-ID-8); the replacement test is under Known limits. Version 1.0.1; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


RS256 JSON Web Token verification with the standard library. RSA PKCS#1 v1.5 verification is integer arithmetic, so
no cryptography package is needed to check a token from Entra ID, the Bot Framework, or any OpenID Connect issuer:
signature, `exp`, `nbf`, `iss` and `aud` are all checked, keys come from the issuer's JWKS and are cached by `kid`,
and the algorithm is pinned to RS256 (no `none`, no HMAC confusion).

## Five-minute start

```python
import json, urllib.request
import jwt_rs256 as J
fetch = lambda url: json.load(urllib.request.urlopen(url, timeout=5))
jwks = J.Jwks(fetch, J.openid_jwks_url(fetch, "https://login.example/.well-known/openid-configuration"))
claims = J.verify(token, jwks, issuers=("https://login.example",), audiences=("my-app",))
```

```
python3 -m unittest discover -s tests -t . -v      # mints tokens with a generated 1024-bit key; never used in production
```

## What is inside

| File | What it is |
| --- | --- |
| `jwt_rs256.py` | `verify`, `Jwks`, `decode_unverified`, `rsa_verify_pkcs1_sha256`, `rsa_sign_pkcs1_sha256` (tests only), `openid_jwks_url` |
| `tests/_rsa.py` | A Miller-Rabin key generator for the tests |
| `tests/test_jwt.py` | A good token passes; signature, expiry, nbf, issuer, audience, `alg: none`, unknown kid, malformed and HMAC-confused tokens are refused |

## How to reuse it

Copy `jwt_rs256.py`. Give `Jwks` a `fetch` that returns parsed JSON (inject a fake in tests). Verify every request
on every route but health; hand the verified claims to your identity layer (`governed-action-loop`'s
`IdentityLibrary` accepts the subject and roles).

## Rules it enforces

Algorithm must be RS256; an unknown `kid` refreshes the JWKS once and then refuses; expiry and not-before with 60 s
leeway; issuer and audience allowlists, `aud` as a string or a list.

## Where it came from

Meg (`meg/responder/jwt.py`, snapshot 2026-09-19), where it verifies Bot Framework and company IdP tokens.

## Known limits

RS256 only (add RS384/512 by changing the DigestInfo prefix). Production never signs here; the sign function exists
for tests.

**Replacement test** (the platform specification's §14.3 rule for an interim): AgentCore's inbound authorizer validates the same issuers and audiences; the verified claims feed the same principal chain.
