"""Live example: a handler that fetches its secret by name at call time and refuses to run without a redeemed reference."""
import os, secrets as S
os.environ["APP_SECRET_PAGERDUTY_API"] = "value-from-the-environment"; os.environ["APP_SECRETS"] = "env"
provider = S.provider_from_env(prefix="APP_")
def acknowledge(args, credential):
    who = S.require_credential(credential, "pagerduty")
    key = provider.get("pagerduty/api")
    return f"acknowledged {args['incident']} as {who} with a key of {len(key)} characters (never logged)"
print(acknowledge({"incident": "PD-1"}, {"audience": "pagerduty", "on_behalf_of": "u_dana"}))
for bad in ({}, {"audience": "jira", "on_behalf_of": "u_dana"}):
    try: acknowledge({"incident": "PD-1"}, bad)
    except S.UpstreamError as e: print("refused:", e)
try: provider.get("missing/secret")
except S.SecretError as e: print("missing name:", e)
