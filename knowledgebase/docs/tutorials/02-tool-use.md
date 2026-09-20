---
title: "Tutorial 2: tool use"
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [tutorial, agents]
audience: [engineer]
---
# Tutorial 2: tool use

## Goal

Let the model call one of your functions, and validate what it sends you.

## Steps

1. Define a tool with a strict schema. The description is a prompt: say when to use it.

   ```python
   TOOLS = [{
       "name": "get_exchange_rate",
       "description": "Return today's reference exchange rate between two ISO currency codes.",
       "input_schema": {
           "type": "object",
           "properties": {"base": {"type": "string"}, "quote": {"type": "string"}},
           "required": ["base", "quote"],
           "additionalProperties": False,
       },
       "strict": True,
   }]
   ```

2. Implement the function, validating inputs yourself even though the schema is strict:

   ```python
   def get_exchange_rate(base: str, quote: str) -> dict:
       if len(base) != 3 or len(quote) != 3:
           return {"error": "currency codes must be three letters"}
       return {"base": base, "quote": quote, "rate": 1.0}  # replace with the reference-rate service
   ```

3. Run the loop with the internal SDK's tool runner: it sends the request, executes your
   function when the model asks, and returns the result until the model finishes.

4. Log every tool call with its input and result. Read the log back: that is your audit trail.

5. Add a deliberately bad request ("convert to GBPX") to see the validation path.

## What you learned

- A tool description is the most important prompt you will write.
- The tool validates; the model is not trusted to.
- Every call is logged.

Next: [Tutorial 3](03-agent-sdk.md).
