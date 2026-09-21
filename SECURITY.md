# Security notes: the collection's deployables

The threat model the platform specification sets (§8, PLT-AC, PLT-DATA, PLT-CAT, PLT-ID) applied to what ships
here. Each row names the control and where its test is.

| Threat | Control | Where |
| --- | --- | --- |
| A forged or replayed token | RS256 through the provider's JWKS, exp/nbf/iss/aud checked, algorithm pinned; mock identity refused in production | `rs256-jwt-verify`, `hub-api/tests/test_oidc.py`, `governed-action-loop/tests/test_production_adapters.py` |
| A person acting beyond their role | Roles come from directory groups through a map the platform team owns; the policy bundle decides per tier; the front end only hides | `hub-api/auth.py`, `actionloop/policy.py`, `hub/src/auth/permits.ts` |
| Prompt injection through a ticket, a page, a tool description | Sources fenced and scored; a tainted context refuses proposals before any model call and caps the session at reads; tool descriptions of external MCP servers scored and pinned | `untrusted-input-guard`, `cited-llm-engine`, `mcp-gateway-client`, the agent's `never` tests |
| The model acting without a person | W1 parks with a hash and runs once after the acting person confirms; W2 needs another person's approval; MONEY forbidden | `governed-action-loop/tests`, `mcp-tool-server` (elicitation) |
| The hub's guide steered by a question or a page | The guide has no tools and only reads a corpus generated from the repository's own pages; a question that reads as an instruction is refused before any ranking or model call, answers are cite-or-drop, and the log carries ids only | `hub-api/guide.py`, `hub-api/tests/test_guide.py`, `hub/src/api/mock/guideRules.ts` |
| A tool outside the catalog | The catalog is built from the template and signed; an unknown tool fails at the catalog hook; an external server's tools are an allowlist | `incident-first-read-agent`, `mcp-gateway-client` |
| A held credential leaking | None held: names resolved at call time, references minted per call and redeemed once per audience, SigV4 from the task role, KMS for signing | `secrets-by-name`, `actionloop/identity.py`, `signing.KmsKey`, connector tests (no token in a URL) |
| PII reaching a model or a log | Results projected to declared shapes and masked; logs ids only; the assistant's citations carry the classification | `dataguard.py`, `ids-only-logging`, `hub-api/tests/test_assistant.py` |
| A person's conversations kept for good | Deleted daily past `HUB_CONVERSATION_RETENTION_DAYS`, feedback rows with them; the setting must be set outside the sandbox | `hub-api/__main__.py` (`retention`), `hub-api/tests/test_ops.py` |
| A tampered record | Hash-chained, verified at every start, exported with its head; a break is an incident | `audit-chain`, `agent-runtime/export.py`, `RUNBOOK.md` |
| One client exhausting the service for everyone | A token bucket per person on the hub's API and on the agent's runs (`429`, `Retry-After`); the bank's gateway limits by network in front of it | `hub-api/ops.py`, `hub-api/tests/test_ops.py`, `agent-runtime/tests/test_ops.py` |
| Script injection into the served hub | Content-Security-Policy on every page: scripts, styles, fonts and images from the hub's origin only, connections to the hub and the identity provider, no inline script; framed by itself alone (the silent-renew frame) and framing only itself and the provider; HSTS behind https | `hub-api/app.py` (`CSP`, `csp_for`), `hub-api/tests/test_ops.py`, `scripts/smoke-oidc.sh` (no violation in a real sign-in) |
| A misconfigured production process | Fail-closed settings: fakes refused, https required, file-backed record, non-environment secrets; the entrypoint checks before listening | `services/*/settings.py`, `scripts/verify.sh` (the refusal gates) |
| An unapproved external request from the hub page | Fonts and assets served from the same origin; the API is same-origin; no CDN | `hub/public/fonts`, `hub-api/app.py` (security headers) |
| Supply chain | Standard library only in every Python deployable; the hub's lockfile pinned; base image digests pinned by the bank; vendored files checked byte for byte | `services/vendor.py`, `tools/shelf.py --check`, `deploy/Dockerfile` |

## Not covered here, by design

The platform's own controls (AgentCore Gateway, Policy, the registry, the conformance suite) replace the interim
pieces; each component's replacement test names the condition. Network policy, WAF and the identity provider's
configuration are the bank's.

## Reporting

A finding goes to the AI security engineers who sign components off; a chain that does not verify is an
incident on the day it is found.
