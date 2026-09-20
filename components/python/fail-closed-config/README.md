# fail-closed-config

Configuration that refuses to start a live process with a missing gate. Everything comes from the environment, an
empty value means unset, secrets are names in the vault (never values), `validate()` returns every problem at once
naming the variable and never its value, and `check-config` is the entrypoint's first command (exit 2 refuses to
listen).

## Five-minute start

```
APP_MODE=live APP_ENV=staging python3 config.py      # config: APP_DB must be a file path ... (exit 2)
python3 config.py                                   # config ok (fake mode in a sandbox)
python3 -m unittest discover -s tests -t . -v
```

```sh
# entrypoint.sh
set -eu
python3 -m myservice check-config
exec python3 -m myservice serve
```

## What is inside

| File | What it is |
| --- | --- |
| `config.py` | `Settings` (`from_env`, `validate`, `require_valid`, `diagnostics`), `check_config`, `ConfigError` |
| `tests/test_config.py` | Fake refused in production; live needs every gate; a complete live set is valid; the environment loader and the exit codes |

## How to reuse it

Copy `config.py`, rename the fields, keep the three rules: live needs a durable store, https, issuers, gates and one
observability target; fake mode is refused in production; `diagnostics()` prints presence and shape only.

## Where it came from

The shape of Meg's `responder/config.py` (snapshot 2026-09-19), reduced to the generic fields.
