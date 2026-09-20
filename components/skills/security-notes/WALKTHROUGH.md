# Walkthrough: security-notes

## 1. Read the live example

`EXAMPLE.md` is the first responder's real security notes at the 2026-09-19 snapshot, names made neutral: a threat-model delta with a control and a code location per row, the data classes, the corpus command and counts, the known limits.

## 2. Start from the template

```
cp components/skills/security-notes/TEMPLATE.md /path/to/your-service/SECURITY.md
```

## 3. Write the delta first

Two sentences: which inputs are now untrusted, which egress paths exist. Then one row per threat. Keep the template's rows that apply (injection per source, replayed confirmation, self-approval, a person outside the gate, an unauthenticated request, a held credential, customer free text, PII, resumed sessions, restart, malformed output, the model acting, budget exhaustion) and add yours.

## 4. Point every row at code

The "where" cell names a file or function that exists. Open each one while writing; a control without a location is not a control.

## 5. Run the corpus and paste the numbers

The corpus command, the class count, the criterion (zero unauthorized actions per release) and where new patterns go.

## 6. Say what is a heuristic and what is interim

Known limits: the injection score is a floor; the signing key is local until the key service; the decisions still open and who owns them.

## 7. Hand it to Security

They verify row by row against the code and sign; the readiness page names that step.
