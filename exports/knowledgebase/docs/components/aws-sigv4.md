---
title: "AWS sigv4"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [security, cost]
audience: [engineer]
---
# aws-sigv4

> A component of the collection: `components/python/aws-sigv4/` in the repository (kind integration, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.14, §4.1 (PLT-AC-9, PLT-KEY-2); the replacement test is under Known limits.


AWS Signature Version 4 with `hmac` and `hashlib` only. Credentials come from the ECS task role (the container
credentials endpoint), the instance role, or the environment, in that order; every request is signed per call. Enough
to call Secrets Manager, CloudWatch, ECS and Bedrock without an SDK in the image.

## Five-minute start

```python
from sigv4 import AwsJson
from httpclient import Http                     # stdlib-http-client
aws = AwsJson(Http(), region="us-east-1")       # credentials from the task role at first use
secret = aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/pagerduty-api"})
```

```
python3 -m unittest discover -s tests -t . -v   # the documented signing-key vector, headers, credential order
```

## What is inside

| File | What it is |
| --- | --- |
| `sigv4.py` | `Credentials`, `load_credentials`, `signing_key`, `sign_request`, `AwsJson.call` (JSON protocol) and `.query` (query protocol, XML back) |
| `tests/test_sigv4.py` | The AWS documentation's key-derivation vector, the header set, credential resolution order, a signed call |

## How to reuse it

Copy `sigv4.py` next to `stdlib-http-client`'s `httpclient.py` (or any object with `request(method, url, headers,
body)`). Keep ARNs and names in configuration, never keys: the task role is the credential.

## Where it came from

Meg (`meg/responder/sigv4.py`, snapshot 2026-09-19), used for Secrets Manager, CloudWatch, ECS and Bedrock Converse.

## Known limits

No presigned URLs, no S3 chunked uploads. Credentials are cached for the process lifetime; restart on rotation.

**Replacement test** (the platform specification's §14.3 rule for an interim): Workload identity and the token vault issue what the task role signs today; no code above the adapter changes.
