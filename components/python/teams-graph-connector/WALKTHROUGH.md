# Walkthrough: teams-graph-connector

## 1. Run the live example

```
cd components/python/teams-graph-connector && python3 example.py
```

The gate check, a war room created, a card posted and pinned, a long answer chunked into numbered parts, and a transient failure raised rather than swallowed.

## 2. Copy the file

```
cp teams_graph.py /path/to/your-service/
```

## 3. Wire the live client

```python
token = AppToken(http, secrets, tenant_id="<tenant-id-placeholder>", app_id="<app-id-placeholder>", secret_name="bot/app-secret")
teams = GraphClient(http, token)
```

The Entra application needs resource-specific consent in the team it serves. Keep the fake for tests and demonstrations; both have the same methods.

## 4. Gate at the surface

Before anything runs, `teams.check_member_groups(user_id, [team_gate, operator_gate])`. An empty gate refuses everyone; that is the fail-closed rule.

## 5. Post through the loop

Make each post a tool on the gateway (`teams___post_message`) so it is a recorded call with a tier. Chunk with `chunk(text)` before posting; every delivery returns an id or raises.

## 6. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
