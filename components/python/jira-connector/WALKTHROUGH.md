# Walkthrough: jira-connector

## 1. Run the live example

```
cd components/python/jira-connector && python3 example.py
```

## 2. Read the handler rule

`handlers()` in `jira.py`: every handler calls `require_credential(credential, audience)` first. The credential
is what the harness's gateway redeemed from the reference the loop minted for this call; without it, nothing runs.

## 3. Run the tests

```
python3 -m unittest discover -s tests -t . -v
```

## 4. Copy it into your project

```
cp components/python/jira-connector/jira.py yourproject/targets/jira.py
```

## 5. Wire it

```python
client = JiraClient(Http(), secrets, "https://<your jira>", "agents/jira-token", user="<service account email>")   # or auth="bearer"
gateway.register_target("tickets", handlers(client, "tickets"))
```

Keep `FakeJira` behind the same registration in the sandbox; `AGENT_TARGETS` in the runtime decides which is used.

## 6. Prove it

Against a sandbox Jira project, read one issue and post one comment through the agent; the comment names the
person, and the chain has the intent record before the write.
