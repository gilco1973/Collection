# comm-templates

Stakeholder and customer messages as owned, versioned templates that a model fills through named fields only. The
model cannot edit a template; free text never leaves the system toward a customer; the customer template carries the
disclosures Compliance requires. `render` refuses unknown fields and missing required ones and returns HTML for a
chat surface and plain text for a pager or a status page.

## Five-minute start

```python
import templates
r = templates.render("status_internal@1", {"incident": "INC-42", "severity": "SEV2", "service": "payments-api",
                                            "status": "mitigating", "impact": "card payments delayed", "next_update_in": "30 min"})
print(r["text"]); print(r["registry_hash"])   # the hash travels with the record so a reviewer knows which text was used
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `templates.py` | `TEMPLATES` (internal status, leadership brief, shift handover, customer status), `render`, `registry_hash`, `TemplateError` |
| `tests/test_templates.py` | Fields only and escaped; missing and unknown fields refused; the disclosure; optional defaults |

## How to reuse it

Copy `templates.py` and replace the texts with your process's and Compliance's; keep `owner` and `audience` on each.
Post the customer template only from a principal with the communications role (a bundle rule in
`governed-action-loop`), and record `registry_hash` with the action.

## Where it came from

Meg (`meg/responder/templates.py`, snapshot 2026-09-19), with the company name in the disclosure made neutral.
