# Walkthrough: untrusted-input-guard

## 1. Run the live example

```
cd components/python/untrusted-input-guard && python3 example.py
```

Two sources, one carrying an instruction and an email. You see the context tainted by that source, the fenced block the model gets (tagged `suspicious="true"`, email masked to `[EMAIL]`), the withheld text people get, the uncited claim dropped, and the proposal refused.

## 2. Copy the two files

```
cp guard.py corpus.py /path/to/your-service/
```

## 3. Build a context per turn

For every piece of upstream text your tools return, `ctx.add(kind, ref, text, origin)`. Kinds are yours (`alert`, `log`, `ticket`, `message`, `code`); `ref` is what a reviewer can open. Code is scored on comments and string literals only.

## 4. Give the model only the fence

Put `SYSTEM_PROMPT_RULES` in the system prompt and `ctx.fenced()` in the user text. Never interpolate raw upstream text into a prompt.

## 5. Check what comes back

Run the model's claims through `check_citations(claims, ctx)`; show only what survives; report `confidence(claims, ctx)`. Show people `source.safe_text`, never `source.text`, and keep the id citable.

## 6. Enforce the ceiling

Before any proposal or write, read `ctx.tainted`. Tainted means reads only for that session. If you use `governed-action-loop`, call `harness.taint(session, ctx.taint_sources, reason)` and the structural check does the rest.

## 7. Keep the corpus green

```
python3 -m unittest discover -s tests -t . -v
```

The corpus test asserts every class taints and benign text does not. Add every pattern you meet in production to `CORPUS`; run it in CI on every release; zero unauthorized actions is the criterion.
