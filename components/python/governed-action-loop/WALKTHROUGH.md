# Walkthrough: governed-action-loop

Ten minutes from a clean checkout to an agent of your own running inside the loop. Every step has the command and what you should see.

## 1. Run the live example

```
cd components/python/governed-action-loop
python3 example.py
```

You see a session admitted at ladder L2, a read returning masked data, a W1 write parked with a hash, the same write running once after the person confirms, a W2 refused for lack of an approval, and the chain verifying with zero gateway disagreements. That is the whole loop in six lines of output.

## 2. Read `example.py` top to bottom

It is the consumer's entire wiring, about ninety lines: three `ToolDecl`s by tier, a rule bundle with four rules, two fake handlers, a result shape per tool, and `build()` that assembles identity, catalog, gateway, audit, kill switches and the harness. Nothing else in the package is touched by a consumer.

## 3. Run the invariants

```
python3 -m unittest discover -s tests -t . -v
```

Fifteen tests, one per rule the loop enforces. Read their names: they are the promises you are adopting.

## 4. Copy the package into your service

```
cp -r actionloop /path/to/your-service/
cp example.py /path/to/your-service/wiring.py
```

Keep `actionloop/` untouched; you will refresh it from the shelf. Everything you change is in `wiring.py`.

## 5. Declare your tools

Replace `TOOLS` with your operations, one `ToolDecl` each: target, operation, tier (`R`, `W1`, `W2`), the contract operation it binds to, the permission, the argument schema. An irreversible tool cannot be `W1`; `C.build` refuses it. Add every contract operation to `CONTRACT_OPS`; a tool bound to an unrecorded one is an "unbacked claim" and fails the build.

## 6. Write the rules

Replace `RULES`: who may read (a role in `principal.roles`), who may confirm a `W1` (the acting person), who may approve a `W2` (`refs.approver` not equal to `$principal.human`, and holding the owner role). Forbid what must never happen. The structural checks you cannot waive are in `actionloop/policy.py`.

## 7. Register handlers and result shapes

One handler per tool on the gateway, `(args, credential) -> dict`. The credential is a redeemed reference; fetch your real secret by name inside the handler (`secrets-by-name`). Declare a result shape per tool: which fields reach the model, and which are identifiers kept verbatim (`"id"`).

## 8. Drive it from your surface

Your chat bot or API calls `harness.admit` with the person's token, then `harness.call` per tool. Catch `Stop`: `needs.input` means render `session.pending` as a confirmation card with its hash; `taint.forbids_tier` means the session saw an injected instruction and is capped to reads; the budget and kill reasons end the turn. Confirm with `harness.confirm(session, person, hash)` and call again with `refs={"confirmation": ref}`.

## 9. Prove it before you ship

Run your own version of the five demonstrations (see the `demonstrations-as-acceptance` practice): replay, a week under confirmation, a game day, the injection corpus (`untrusted-input-guard`), chaos. Each is a command that prints numbers.

## What to read next

`README.md` for the rules and the replacement test; `untrusted-input-guard` for the taint side; `cited-llm-engine` for the think step that proposes without acting.
