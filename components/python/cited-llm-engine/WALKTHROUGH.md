# Walkthrough: cited-llm-engine

## 1. Run the live example

```
cd components/python/cited-llm-engine && python3 example.py
```

The rules engine names the deploy as the cause with cited claims; a fake model's answer keeps only the claim that cites a real source; a proposal on a tainted context is refused before the model is called.

## 2. Copy the two files

```
cp engine.py guard.py /path/to/your-service/
```

## 3. Define your stages

Each `Stage` has a name, the JSON schema as prose, instructions, and `proposes_action=True` if the output could become a write. Keep the three examples as a starting point.

## 4. Plug in a model

`ModelEngine(complete)` where `complete(system, user) -> text` is anything: `governed-action-loop`'s model gateway (recommended, for the allowlist, prompt hash and budget), an SDK, an internal endpoint. Keep `RulesEngine` as the offline and degraded mode.

## 5. Turn answers into actions only through the loop

An engine answer is advisory JSON. Your command layer turns a proposal into a tool call through the harness, where the tier and the person's confirmation decide.

## 6. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
