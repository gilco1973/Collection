"""Communication templates: owned by a process and by Compliance, versioned, hashed with the catalog, and filled by
the model only through named fields. The model cannot edit a template;
free text never leaves the platform toward a customer.

`render(ref, fields)` refuses unknown fields and missing required ones and returns HTML for Teams and a
plain-text form for PagerDuty or the status page. The customer template carries the required disclosures.
"""
from __future__ import annotations
import html, re
import hashlib, json

TEMPLATES = {
    "status_internal@1": {"owner": "incident-process", "audience": "internal", "required": ("incident", "severity", "service", "status", "impact", "next_update_in"), "optional": ("hypothesis", "actions"),
        "html": "<b>Incident {incident} · {severity} · {service}</b><br/>Status: {status}<br/>Impact: {impact}<br/>Working hypothesis: {hypothesis}<br/>Actions so far: {actions}<br/>Next update in {next_update_in}."},
    "leadership@1": {"owner": "incident-process", "audience": "leadership", "required": ("incident", "severity", "service", "customer_impact", "status", "eta"), "optional": ("commander",),
        "html": "<b>Leadership brief · {incident} ({severity})</b><br/>Service: {service}<br/>Customer impact: {customer_impact}<br/>Status: {status}<br/>Expected resolution: {eta}<br/>Incident commander: {commander}"},
    "handover@1": {"owner": "incident-process", "audience": "internal", "required": ("incident", "outgoing", "incoming", "status", "open_watches", "pending_confirmations", "next_steps"), "optional": (),
        "html": "<b>Shift handover · {incident}</b><br/>From {outgoing} to {incoming}<br/>Status: {status}<br/>Open watches: {open_watches}<br/>Pending confirmations: {pending_confirmations}<br/>Next steps: {next_steps}<br/>The incoming engineer becomes commander on acknowledgement."},
    "customer_status@1": {"owner": "compliance", "audience": "customer", "required": ("service_public_name", "status", "impact_public", "next_update_in"), "optional": (),
        "html": "<b>{service_public_name}: service status</b><br/>Current status: {status}<br/>What you may notice: {impact_public}<br/>Next update in {next_update_in}.<br/><i>{disclosure}</i>",
        "disclosure": "The company is monitoring this issue. No customer data is known to be affected; we will update this notice if that changes. For account questions contact Customer Support."},
}

_FIELD = re.compile(r"{([a-z_]+)}")


class TemplateError(Exception):
    pass


def registry_hash() -> str:
    return "sha256:" + hashlib.sha256(json.dumps(TEMPLATES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render(ref: str, fields: dict) -> dict:
    t = TEMPLATES.get(ref)
    if not t: raise TemplateError(f"unknown template {ref}")
    allowed = set(t["required"]) | set(t["optional"])
    unknown = set(fields) - allowed
    if unknown: raise TemplateError(f"{ref}: fields not in the template: {sorted(unknown)}")
    missing = [f for f in t["required"] if not str(fields.get(f, "")).strip()]
    if missing: raise TemplateError(f"{ref}: required fields missing: {missing}")
    vals = {k: html.escape(str(fields.get(k, "—")))[:600] for k in allowed}
    if "disclosure" in t: vals["disclosure"] = html.escape(t["disclosure"])
    out = t["html"]
    for k in _FIELD.findall(out):
        out = out.replace("{" + k + "}", vals.get(k, "—"))
    text = re.sub(r"<br\s*/?>", "\n", out); text = re.sub(r"<[^>]+>", "", text)
    return {"template": ref, "audience": t["audience"], "owner": t["owner"], "html": out, "text": html.unescape(text), "registry_hash": registry_hash()}
