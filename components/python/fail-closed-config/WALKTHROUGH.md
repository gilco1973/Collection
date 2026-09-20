# Walkthrough: fail-closed-config

## 1. Run the live example

```
cd components/python/fail-closed-config && python3 example.py
```

Fake mode in a sandbox is valid; live mode with nothing set lists every problem by variable name; a complete live set is valid and its diagnostics show presence only; `check-config` returns 2 for a memory store in live mode.

## 2. Copy and rename the fields

```
cp config.py /path/to/your-service/
```

Keep `from_env`, `validate`, `require_valid`, `diagnostics` and `check_config`. Rename the fields to yours; keep the three rules: live needs a durable store, https, issuers, gates and one observability target; fake mode is refused in production; diagnostics never print a value.

## 3. Make it the container's first command

```sh
set -eu
python3 -m yourservice check-config
exec python3 -m yourservice serve
```

## 4. Test the gate

Set one gate to empty and start the container; it must exit 2 before listening. Keep that as a test.
