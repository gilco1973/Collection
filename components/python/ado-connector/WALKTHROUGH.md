# Walkthrough: ado-connector

## 1. Run the live example

```
cd components/python/ado-connector && python3 example.py
```

## 2. Read the service map

`handlers()` in `ado.py` takes `pipelines`: the only pipelines the agent can reach, by service name. The template
says `deploys.recent {service}`; the id never appears in a prompt or an argument.

## 3. Run the tests

```
python3 -m unittest discover -s tests -t . -v
```

## 4. Copy it

```
cp components/python/ado-connector/ado.py yourproject/targets/ado.py
```

## 5. Wire it

```python
client = AdoClient(Http(), secrets, "https://dev.azure.com/<org>", "<project>", "agents/ado-pat")
gateway.register_target("deploys", handlers(client, "deploys", pipelines={"checkout": 42}))
```

## 6. Prove it

Read the latest deploy of one service in a sandbox project through the agent; the minutes-before-the-trigger
figure matches the pipeline's run page.
