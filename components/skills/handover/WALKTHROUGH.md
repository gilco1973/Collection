# Walkthrough: handover

## 1. Read the live example

`EXAMPLE.md` is the first responder's second handover: the header, what it is with the commands and last numbers, what changed since the first, tickets completed with "remains on the account" per row, decisions with their reversal, the layout, what it does not do, the path to staging.

## 2. Start from the template

```
cp components/skills/handover/TEMPLATE.md /path/to/your-service/HANDOVER.md
```

## 3. Run everything and paste the numbers

Tests, demonstrations, checks: from this machine, today. The next person will run the same commands and expect the same numbers.

## 4. Two halves per ticket

"Done here" is the code and tests that exist with fakes where needed; "remains on the company's account" is the step that closes the ticket. Never claim the second half.

## 5. Decisions with a reversal path

Each decision taken while building, and how the specification's next revision undoes it if it disagrees.

## 6. Version it and package it

Add a row to the history table, bump the version in the package name, build the package from the tracked files plus this document. Keep the page under 200 lines; link detail out.
