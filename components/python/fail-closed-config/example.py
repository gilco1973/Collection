"""Live example: the same settings in fake and live mode; live refuses to start until every gate is set, and never prints a value."""
import os, config
print("fake in a sandbox:", config.Settings().validate() or "valid")
live = config.Settings(mode="live", env="staging")
print("live with nothing set:"); [print("  -", p) for p in live.validate()]
ok = config.Settings(mode="live", env="staging", db_path="/var/app/app.db", public_base_url="https://app.example", idp_issuer="https://idp.example", idp_audience="app",
                     team_gate_group_ids=("group-id-placeholder",), operator_group_id="group-id-placeholder-2", observability_targets=("elastic",))
print("live, complete:", ok.validate() or "valid"); print("diagnostics (no values):", ok.diagnostics())
os.environ.update({"APP_MODE": "live", "APP_ENV": "staging", "APP_DB": ":memory:"}); print("check-config exit code:", config.check_config())
for k in ("APP_MODE", "APP_ENV", "APP_DB"): os.environ.pop(k)
