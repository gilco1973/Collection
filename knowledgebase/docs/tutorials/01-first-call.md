---
title: "Tutorial 1: your first model call"
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [tutorial, prompting]
audience: [new-hire, engineer]
---
# Tutorial 1: your first model call

## Goal

Call a model through the gateway, with the data-classification header, and find the
request in the gateway log.

## Steps

1. Create a project on the paved Python stack:

   ```bash
   poetry new first-call && cd first-call
   poetry add bank-ai-sdk   # internal bundle: vendor SDK + gateway defaults
   ```

2. Export your development gateway key. It is a gateway key, not a vendor key:

   ```bash
   export AI_GATEWAY_API_KEY=...   # from the service catalog request on day one
   ```

3. Write `first_call.py`:

   ```python
   from bank_ai.gateway import client

   response = client.messages.create(
       model="assistant-default",
       max_tokens=512,
       system="You write for bank employees. Be concise and cite nothing you were not given.",
       messages=[{"role": "user", "content": "In three bullets, what is a paved road?"}],
       extra_headers={"X-Data-Classification": "internal"},
   )
   for block in response.content:
       if block.type == "text":
           print(block.text)
   print("request id:", response._request_id)
   ```

4. Run it, copy the request id, and find the entry in the gateway log viewer. Note the
   token counts and the logical-to-concrete model mapping.

5. Change the header to `confidential` and run again. Observe that the prompt is now
   logged as a hash. Change it to `restricted` and observe the rejection.

## What you learned

- Where credentials live (the gateway, not your code).
- That classification is enforced, not advisory.
- How to trace a request end to end.

Next: [Tutorial 2](02-tool-use.md).
