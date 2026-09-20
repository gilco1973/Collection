#!/usr/bin/env python3
"""The diagrams the documents and the video share, drawn once with reportlab's vector shapes.

    python3 docs/pdf/diagrams.py --svg <dir>     # writes architecture.svg, harness.svg, signoff.svg, assistant.svg (for the slides)
In the PDFs the same drawings are embedded as vectors. Colours are the hub's; no image files are involved.
"""
from __future__ import annotations
import math, os, sys
from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors

INK, ACCENT, MUTED, LINE = colors.HexColor("#1b1f24"), colors.HexColor("#1f4e9c"), colors.HexColor("#5b6470"), colors.HexColor("#9aa4b1")
FILL = {"hub": colors.HexColor("#e8f0fb"), "bank": colors.HexColor("#fdf3e3"), "loop": colors.HexColor("#e9f7ee"), "person": colors.HexColor("#f3e9fb"), "plain": colors.HexColor("#f2f5f9"), "warn": colors.HexColor("#fde8e6")}


def box(d, x, y, w, h, title, sub=None, kind="plain", size=9):
    d.add(Rect(x, y, w, h, rx=6, ry=6, fillColor=FILL[kind], strokeColor=LINE, strokeWidth=0.8))
    d.add(String(x + w / 2, y + h / 2 + (3 if sub else -3), title, fontName="Helvetica-Bold", fontSize=size, fillColor=INK, textAnchor="middle"))
    if sub:
        for i, line in enumerate(sub.split("\n")):
            d.add(String(x + w / 2, y + h / 2 - 8 - i * 9, line, fontName="Helvetica", fontSize=size - 1.5, fillColor=MUTED, textAnchor="middle"))


def arrow(d, x1, y1, x2, y2, label=None, dashed=False, both=False):
    d.add(Line(x1, y1, x2, y2, strokeColor=ACCENT, strokeWidth=1, strokeDashArray=[3, 2] if dashed else None))
    ang = math.atan2(y2 - y1, x2 - x1)
    for (ex, ey, a) in ((x2, y2, ang), (x1, y1, ang + math.pi)) if both else ((x2, y2, ang),):
        p = [ex, ey, ex - 6 * math.cos(a - 0.4), ey - 6 * math.sin(a - 0.4), ex - 6 * math.cos(a + 0.4), ey - 6 * math.sin(a + 0.4)]
        d.add(Polygon(p, fillColor=ACCENT, strokeColor=ACCENT))
    if label:
        d.add(String((x1 + x2) / 2, (y1 + y2) / 2 + 4, label, fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="middle"))


def architecture() -> Drawing:
    """Where each piece runs and what it talks to, inside the bank."""
    d = Drawing(520, 300)
    d.add(Rect(6, 6, 508, 288, rx=8, ry=8, fillColor=None, strokeColor=LINE, strokeWidth=0.6, strokeDashArray=[4, 3]))
    d.add(String(14, 282, "Inside the bank's network. Nothing is fetched from the public internet.", fontName="Helvetica-Oblique", fontSize=7.5, fillColor=MUTED))
    box(d, 20, 200, 110, 52, "The hub", "in the browser;\nreads /config.js at start", "hub")
    box(d, 200, 200, 130, 52, "hub-api", "the hub's API + the built hub;\none container, a record file", "hub")
    box(d, 200, 100, 130, 52, "agent runtime", "one agent: template + harness;\n/mcp and /runs, a record file", "loop")
    box(d, 20, 118, 110, 44, "Platform runtime", "owns the assistant\n(optional relay)", "plain")
    box(d, 20, 24, 110, 52, "MCP clients", "Claude Code, the hub's\nassistant, a partner client", "hub")
    box(d, 390, 236, 112, 40, "Identity provider", "OIDC, RS256, groups", "bank")
    box(d, 390, 188, 112, 40, "Knowledge base", "pages and /search", "bank")
    box(d, 390, 140, 112, 40, "Bedrock", "the model, VPC endpoint", "bank")
    box(d, 390, 92, 112, 40, "Jira, Azure DevOps", "tickets, deploys", "bank")
    box(d, 390, 44, 112, 40, "KMS, Secrets, S3", "signing, names, audit", "bank")
    arrow(d, 130, 226, 200, 226, "https, bearer", both=True)
    arrow(d, 130, 56, 200, 112, "MCP", both=True)
    arrow(d, 200, 206, 130, 150, "relay turns", dashed=True)
    arrow(d, 330, 244, 390, 256); arrow(d, 330, 226, 390, 208); arrow(d, 330, 208, 390, 160, dashed=True)
    arrow(d, 330, 146, 390, 248); arrow(d, 330, 132, 390, 156); arrow(d, 330, 120, 390, 112); arrow(d, 330, 108, 390, 64)
    d.add(String(360, 268, "verify tokens", fontName="Helvetica", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
    d.add(String(345, 200, "cite pages", fontName="Helvetica", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
    d.add(String(360, 96, "read; a W1 write", fontName="Helvetica", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
    d.add(String(360, 74, "sign, names, export", fontName="Helvetica", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
    return d


def harness() -> Drawing:
    """What happens to one call an agent makes. The three hooks are fixed; the model never bypasses them."""
    d = Drawing(520, 300)
    d.add(String(260, 288, "One call through the loop. Reads run; a write waits for the acting person; a bigger change needs a second person; money is forbidden.", fontName="Helvetica-Oblique", fontSize=7.2, fillColor=MUTED, textAnchor="middle"))
    box(d, 10, 220, 95, 48, "The agent", "wants to call a tool\n(the model, or a person)", "loop")
    box(d, 125, 220, 120, 48, "Hook 1: before", "kill switch? in the catalog?\narguments valid? policy?", "loop")
    box(d, 265, 220, 110, 48, "The gateway", "redeems a reference,\nruns the target's client", "plain")
    box(d, 395, 220, 115, 48, "Jira, deploys, ...", "the real system, or its\nfake in the sandbox", "bank")
    box(d, 10, 138, 95, 48, "Dual control", "W2: another person's\napproval is required", "person")
    box(d, 125, 138, 120, 48, "Parked", "W1: the acting person\nconfirms the exact call once", "person")
    box(d, 265, 138, 110, 48, "Refused", "tainted session, above the\nladder, no scope, kill switch", "warn")
    box(d, 125, 40, 120, 48, "The answer", "masked text and ids;\nthe session tainted if it scored", "plain")
    box(d, 265, 40, 110, 48, "Hook 3: record", "every call, decision and\nconfirmation on the chain", "loop")
    box(d, 395, 40, 115, 48, "Hook 2: after", "project to the declared\nshape; mask; score", "loop")
    arrow(d, 105, 244, 125, 244); arrow(d, 245, 244, 265, 244, "allow"); arrow(d, 375, 244, 395, 244)
    arrow(d, 185, 220, 185, 186, "W1"); arrow(d, 235, 220, 300, 186, "deny"); arrow(d, 135, 220, 70, 186, "W2", dashed=True)
    arrow(d, 452, 220, 452, 88); arrow(d, 395, 64, 375, 64); arrow(d, 265, 64, 245, 64)
    arrow(d, 185, 138, 185, 88, "confirmed: runs once", dashed=True)
    return d


def signoff() -> Drawing:
    """A component's way to the shelf and how a sign-off becomes a record."""
    d = Drawing(520, 190)
    stages = [("1 scaffolded", "a manifest, placeholders"), ("2 built", "README, walkthrough,\nexample, tests green"), ("3 used once", "the owner names\nthe project"), ("4 owner signed", "by name, at this\nversion"), ("5 security signed", "by role, at this\nversion"), ("6 on the shelf", "GA on the hub and\nin the knowledge base")]
    for i, (t, s) in enumerate(stages):
        x = 10 + i * 85
        box(d, x, 120, 78, 50, t, s, "loop" if i == 5 else ("person" if i in (3, 4) else "plain"), size=8)
        if i < 5: arrow(d, x + 78, 145, x + 85, 145)
    d.add(String(260, 105, "A version bump returns a component to stage 3: both people sign the new version.", fontName="Helvetica-Oblique", fontSize=7.2, fillColor=MUTED, textAnchor="middle"))
    box(d, 10, 20, 120, 60, "The form on the hub", "four attestations, the first\nreal use; the server\nrefuses a missing one", "hub")
    box(d, 200, 20, 120, 60, "The export", "the queue's file, applied\nby the shelf tool after\nre-running the tests", "plain")
    box(d, 390, 20, 120, 60, "The commit", "the manifest is the record;\nthe commit is the\nsignature", "loop")
    arrow(d, 130, 50, 200, 50); arrow(d, 320, 50, 390, 50)
    return d


def assistant() -> Drawing:
    """How the employee assistant answers, and where it stops."""
    d = Drawing(520, 150)
    box(d, 10, 80, 90, 48, "A question", "typed in the hub", "hub")
    box(d, 120, 80, 100, 48, "The guard", "scores the question and\nevery source for injection", "loop")
    box(d, 240, 80, 100, 48, "Knowledge base", "search: the pages that\nmatch, fenced as sources", "bank")
    box(d, 360, 80, 100, 48, "The model", "answers from the sources\nonly, in a fixed shape", "bank")
    box(d, 360, 10, 100, 44, "The answer", "every claim cited or\ndropped; sources shown", "hub")
    box(d, 120, 10, 100, 44, "Stopped", "a source or the question\nread as an instruction", "warn")
    arrow(d, 100, 104, 120, 104); arrow(d, 220, 104, 240, 104); arrow(d, 340, 104, 360, 104); arrow(d, 410, 80, 410, 54); arrow(d, 170, 80, 170, 54, "taint")
    d.add(String(260, 138, "The assistant never changes a system. It reads pages and cites them; anything that looks like an instruction stops it before the model is called.", fontName="Helvetica-Oblique", fontSize=7.2, fillColor=MUTED, textAnchor="middle"))
    return d


ALL = {"architecture": architecture, "harness": harness, "signoff": signoff, "assistant": assistant}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--svg":
        os.makedirs(sys.argv[2], exist_ok=True)
        for name, fn in ALL.items():
            path = os.path.join(sys.argv[2], f"{name}.svg")
            renderSVG.drawToFile(fn(), path)
            svg = open(path, encoding="utf-8").read()
            for rl, web in (("Helvetica-Bold", "Helvetica, Arial, sans-serif; font-weight: bold"), ("Helvetica-Oblique", "Helvetica, Arial, sans-serif; font-style: italic"), ("Helvetica", "Helvetica, Arial, sans-serif")):
                svg = svg.replace(f"font-family: {rl};", f"font-family: {web};")
            open(path, "w", encoding="utf-8").write(svg)
            print("wrote", os.path.join(sys.argv[2], f"{name}.svg"))
    else:
        print(__doc__)
