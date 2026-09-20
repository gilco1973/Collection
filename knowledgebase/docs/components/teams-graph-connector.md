---
title: "Teams graph connector"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, atlassian]
audience: [engineer]
---
# teams-graph-connector

> A component of the collection: `components/python/teams-graph-connector/` in the repository (kind integration, python, status ready). Copy it from there; this page is its README, published by the catalog tool.


Microsoft Teams as a bot's surface, through Graph and the Bot Framework connector: transitive group membership for
gates, war-room channels, proactive posts and Adaptive Cards, pins, change-notification subscriptions, and a
4,000-character chunker that numbers the parts. Every proactive delivery returns an id or raises; nothing fails
silently. The in-memory `FakeTeams` has the same method surface for tests and demonstrations.

## Five-minute start

```python
from teams_graph import FakeTeams, chunk
t = FakeTeams(); t.add_user("u_dana", ["g-oncall"])
room = t.create_channel("team-id", "inc-42 payments-api", "war room")
for part in chunk(long_answer): t.post_message("team-id", room["channel_id"], part)
```

Live: `GraphClient(http, AppToken(http, secrets, tenant_id, app_id, "bot/app-secret"))` with `stdlib-http-client`
and `secrets-by-name`; the same calls, real ids back.

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `teams_graph.py` | `chunk`, `AppToken` (client credentials, cached until shortly before expiry), `GraphClient` (`check_member_groups`, `create_channel`, `post_message`, `post_card`, `pin_message`, `archive_channel`, `add_member`, `reply_via_connector`, subscriptions, `get_message`, `list_messages`), `FakeTeams`, `UpstreamError` |
| `tests/test_teams.py` | Chunking bounds and numbering, the fake's lifecycle and loud failures, the live client against a recording double |

## How to reuse it

Copy `teams_graph.py`. Wire it behind a gateway target so every post is a recorded tool call, and put the gate check
(`check_member_groups`) at the surface before anything runs. The Entra application needs resource-specific consent
for the team it serves; the manifest permissions are listed in Meg's deploy notes.

## Where it came from

Meg (`meg/responder/clients/graph.py`, snapshot 2026-09-19). Renamed ids in the fake; otherwise as is.

## Known limits

Basic change notifications only (ids, no encryption certificate). No message editing or reactions.
