# Walkthrough: secrets-by-name

## 1. Run the live example

```
cd components/python/secrets-by-name && python3 example.py
```

A handler fetches its key by name at call time, refuses two calls without a redeemed reference, and a missing name is an error naming the name.

## 2. Copy the file

```
cp secrets.py /path/to/your-service/
```

## 3. Choose the provider by environment

`APP_SECRETS=env` in tests (`APP_SECRET_PAGERDUTY_API=...`), `file:/path.json` in a sandbox, `aws` in production (with `aws-sigv4`'s `AwsJson`). Configuration carries names like `app/pagerduty-api`, never values.

## 4. Fetch inside the call

Every client receives the provider and the secret name, and calls `provider.get(name)` inside the method. Rotation is a change in the vault; nothing restarts.

## 5. Refuse without a reference

In every gateway handler, first line: `who = require_credential(credential, "<audience>")`. The loop mints a reference bound to the audience and the run; a handler for another audience, or a call outside the loop, has none and refuses.

## 6. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
