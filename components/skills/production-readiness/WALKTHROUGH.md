# Walkthrough: production-readiness

## 1. Read the live example

`EXAMPLE.md` is the first responder's readiness page at increment 3: every row DONE with evidence and numbers, WRITTEN for descriptors not yet applied, OPEN with an owner for account-bound steps, and the closing paragraph on what "production ready" means.

## 2. Start from the template

```
cp components/skills/production-readiness/TEMPLATE.md /path/to/your-service/PRODUCTION-READINESS.md
```

## 3. One row per area

Functional per increment, security, identity, credentials, data, record, metrics, resilience, delivery, packaging, deployment, CI, model risk, and whatever your service adds.

## 4. Run the evidence, do not remember it

For every DONE row, run the test or demonstration today and paste the count. Adjectives are not evidence.

## 5. Name an owner for every OPEN row

A role or a person, never "TBD". An OPEN row without an owner is a design gap, and the page must not pretend otherwise.

## 6. Date it and keep it

The header carries today's date and the branch. At every increment, re-run the evidence and update the rows; the next reviewer runs one command at random.
