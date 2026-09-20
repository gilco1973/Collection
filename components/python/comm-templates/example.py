"""Live example: a status update and a customer notice rendered from templates; a free-text field refused."""
import templates
r = templates.render("status_internal@1", {"incident": "INC-42", "severity": "SEV2", "service": "payments-api", "status": "mitigating", "impact": "card payments delayed <5 min", "next_update_in": "30 min"})
print(r["text"]); print("registry hash:", r["registry_hash"][:22] + "...")
c = templates.render("customer_status@1", {"service_public_name": "Card payments", "status": "degraded", "impact_public": "some payments may take longer", "next_update_in": "1 hour"})
print("---"); print(c["text"])
try: templates.render("customer_status@1", {"service_public_name": "Card payments", "status": "s", "impact_public": "i", "next_update_in": "1h", "free_text": "we think it was the deploy"})
except templates.TemplateError as e: print("refused:", e)
