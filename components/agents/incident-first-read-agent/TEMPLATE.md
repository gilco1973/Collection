# Incident first read: the template

The template is what makes this an agent rather than a script: it says who the agent is, what it may call and
at which tier, which stages it runs, and what it never does. The code loads it as data (`agent.load_template`)
and builds the harness's signed catalog from its `tools`, so the agent can call exactly what is listed here and
nothing else. Change the template, and the catalog, the policy and the listing on the hub change with it.

```json
{
  "name": "incident-first-read",
  "role": "the first read of an incident: an assistant that reads the ticket and the recent deploys, says what changed and what is failing, cites every claim to a source, and proposes at most one action for a person to confirm",
  "ladder": "L2",
  "road": "R2",
  "channel": "operator",
  "stages": ["first-read", "propose"],
  "budget": {"tokens": 20000, "tool_calls": 12, "time_s": 300},
  "tools": [
    {"target": "tickets", "op": "get", "tier": "R", "contract": "tickets.get", "permission": "tickets:read",
     "args": {"key": {"type": "str", "required": true}}, "result": {"key": "id", "title": true, "body": true},
     "classes": "internal", "note": "the incident ticket: title and body, projected and masked before the model sees them"},
    {"target": "deploys", "op": "recent", "tier": "R", "contract": "deploys.recent", "permission": "deploys:read",
     "args": {"service": {"type": "str", "required": true}}, "result": {"run_id": "id", "service": "id", "minutes_before_trigger": "id", "notes": true},
     "classes": "internal", "note": "the last deploy of the service and how long before the trigger it finished"},
    {"target": "tickets", "op": "comment", "tier": "W1", "contract": "tickets.comment", "permission": "tickets:write",
     "args": {"key": {"type": "str", "required": true}, "body": {"type": "str", "required": true}}, "result": {"id": "id"},
     "classes": "internal", "note": "posts the first read on the ticket; parked until the acting person confirms the exact call once"}
  ],
  "never": [
    "posts, changes or rolls anything back without a person confirming the exact tool and arguments",
    "proposes an action on a tainted context; the proposal is refused before any model call",
    "calls anything not listed under tools; the catalog is built from this list and signed",
    "sees raw upstream text; every source is projected to its declared result shape, masked and fenced"
  ]
}
```

## Reading it

- `role` is the sentence the think step's system prompt starts with; `stages` are the stage prompts it runs (`first-read`, `ask`, `propose`), from the cited engine.
- `ladder` is the highest autonomy the agent is registered for; the harness lowers it to the person's own and to L1 on taint.
- `tools` is the whole catalog: target, operation, tier, the contract operation and permission the policy maps it to, the argument schema, and the result shape the data guard projects to (`"id"` keeps a field verbatim, `true` keeps it as text to mask and score).
- `never` is the list the tests prove, one test per line.
