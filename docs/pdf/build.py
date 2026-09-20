#!/usr/bin/env python3
"""Build the three PDFs: the user manual (non-technical), the technical guide, the leadership brief.

    python3 docs/pdf/build.py        # writes docs/pdf/*.pdf (reportlab; screenshots from docs/pdf/img/)
"""
from __future__ import annotations
import datetime, os
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
DATE = datetime.date(2026, 9, 20).strftime("%d %B %Y")
INK, ACCENT, MUTED, LINE, SOFT = colors.HexColor("#1b1f24"), colors.HexColor("#1f4e9c"), colors.HexColor("#5b6470"), colors.HexColor("#d5dae1"), colors.HexColor("#f2f5f9")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=26, leading=32, textColor=INK, alignment=TA_LEFT, spaceAfter=6),
    "sub": ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica", fontSize=12.5, leading=17, textColor=MUTED, spaceAfter=18),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=INK, spaceBefore=16, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=12, spaceAfter=5),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10.2, leading=14.5, textColor=INK, spaceAfter=7),
    "small": ParagraphStyle("sm", parent=ss["Normal"], fontName="Helvetica", fontSize=8.6, leading=11.5, textColor=MUTED),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=INK),
    "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.8, leading=11.5, textColor=INK),
    "code": ParagraphStyle("code", parent=ss["Code"], fontName="Courier", fontSize=8.4, leading=11, backColor=SOFT, borderPadding=(4, 6, 4, 6), leftIndent=4, spaceAfter=8),
    "callout": ParagraphStyle("co", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=INK, backColor=SOFT, borderPadding=(8, 10, 8, 10), spaceBefore=4, spaceAfter=10),
}


def P(text, style="body"):
    return Paragraph(text, S[style])


def H1(t): return P(t, "h1")
def H2(t): return P(t, "h2")


def bullets(items):
    return ListFlowable([ListItem(P(i), leftIndent=12, value="•") for i in items], bulletType="bullet", start="•", leftIndent=14, bulletFontSize=8, spaceAfter=6)


def steps(items):
    return ListFlowable([ListItem(P(i), leftIndent=14) for i in items], bulletType="1", leftIndent=16, bulletFontName="Helvetica-Bold", bulletFontSize=9.5, spaceAfter=6)


def table(rows, widths=None, header=True):
    data = [[Paragraph(c, S["cellb"] if header and i == 0 else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header: style.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(style)); t.spaceAfter = 10
    return t


def shot(name, caption, width=160 * mm):
    path = os.path.join(IMG, name)
    if not os.path.exists(path):
        return P(f"[screenshot: {caption}]", "small")
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(path).getSize()
    height = min(width * h / w, 120 * mm)
    img = Image(path, width=width, height=height, kind="proportional")
    return KeepTogether([img, Spacer(1, 3), P(caption, "small"), Spacer(1, 8)])


def cover(story, title, subtitle, audience):
    story += [Spacer(1, 60 * mm), P(title, "title"), P(subtitle, "sub"), Spacer(1, 6),
              table([["For", audience], ["Date", DATE], ["Status", "Reflects the repository at the date above; the readiness page in the repository is the live record"]], widths=[30 * mm, 130 * mm], header=False),
              PageBreak()]


def build(filename, title, story_fn):
    path = os.path.join(HERE, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=title, author="The AI champions programme", subject=title)

    def deco(canvas, d):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(MUTED)
        if d.page > 1:
            canvas.drawString(20 * mm, 287 * mm, title); canvas.drawRightString(190 * mm, 287 * mm, f"Page {d.page}")
            canvas.setStrokeColor(LINE); canvas.line(20 * mm, 285 * mm, 190 * mm, 285 * mm)
        canvas.drawString(20 * mm, 10 * mm, "Internal. Placeholders in capitals are not real identifiers. Nothing here is a credential.")
        canvas.restoreState()

    story = []
    story_fn(story)
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return path


# =====================================================================================================================
# 1. The user manual (non-technical)
# =====================================================================================================================

def manual(story):
    cover(story, "The AI Hub and the Collection", "A user manual for employees and AI champions: what is there, how to use it, and who to ask.",
          "Everyone who signs in to the hub; AI champions; component owners; AI security engineers")
    story += [H1("1. What this is, in plain words"),
              P("The <b>AI Hub</b> is the front door to the company's AI services. You sign in with your normal work account, see what you may use, open an assistant, and ask for access to the rest. "
                "Behind it is the <b>Collection</b>: a shelf of ready-made AI building blocks that engineers reuse instead of rebuilding, each one checked, versioned and signed off by two people before it is called ready."),
              P("You do not need to know how any of it works to use it. This manual walks through the screens in the order you will meet them, then explains the two things that involve people beyond just using it: "
                "proposing a new AI use for your team, and signing a building block off if you are its owner or an AI security engineer."),
              P("<b>Three rules the hub keeps for you.</b> An assistant only answers from sources it can cite, and shows them. Anything that would change a system waits for a person to confirm it. "
                "Nothing you type is used to change the assistant's instructions; text is treated as a question, never as a command.", "callout"),
              H1("2. Signing in"),
              P("Open the hub's address in your browser and sign in with your company account; the identity provider does the work and the hub never sees your password. "
                "What you see afterwards depends on your role and team: the hub shows only what you may use, and lets you ask for the rest. If a screen you expected is missing, that is access, not a fault; the request button is on the page."),
              H1("3. Discover: what you may use today"),
              P("Discover is the catalog. The top row is what is already open to you. Below it, tabs group everything else: assistants, agents, knowledge, tools, and the paved roads (the approved ways to build something new). "
                "The search box at the top finds any of them by name or by what they do."),
              shot("discover.png", "Discover with the Agents tab open. Each card names the service, its road, whether it is generally available or in preview, and how you reach it."),
              P("A card says one of four things about access: <b>Open</b> (click to use it), <b>Request access</b> (one click sends the request to your lead), <b>View</b> (you can read about it, your role does not use it), or <b>Contract</b> (a service another team runs; the page says who to ask)."),
              H1("4. A listing page"),
              P("Every service and every building block has a page. Read it top to bottom: what it does, what it can read and do (each operation with its tier, from read-only to changes that need confirmation), the evidence behind it (tests, a step-by-step walkthrough, a live example, the knowledge base page), the owner and how to get support, and its versions."),
              shot("listing.png", "A listing page. The right column carries the sign-off card, the getting-started steps, the owner and the versions."),
              P("The chip row under the title tells you at a glance: the road, the language, whether it is ready, which parts of the platform design it implements, and its tags. A component that both its owner and an AI security engineer have signed is marked <b>signed</b>; otherwise the hub shows it as a preview."),
              H1("5. The employee assistant"),
              P("Open the assistant from Discover or from your workspace, type a question, and read the answer. Three things are worth knowing:"),
              bullets(["<b>Citations.</b> Claims in an answer are marked, and the sources appear under it with their classification. A claim without a source is shown as unsupported; treat it as a hint, not a fact.",
                       "<b>Tool calls.</b> When the assistant looks something up, the step appears in the conversation with what it searched for. You can see what it did, not only what it said.",
                       "<b>Feedback and handoff.</b> Each answer ends with one question: did this answer yours? Answer it; it is how the assistant is measured. If you would rather talk to a person, use the handoff and the conversation is routed to one."]),
              P("If the assistant answers that a source looked like an instruction rather than evidence and it did not use it, that is the protection working: something in a page or a ticket tried to steer it. Rephrase, or open the page directly.", "callout"),
              H1("6. Your workspace"),
              P("My workspace gathers what is yours: the assistants you use, your team's services and where each is in its journey to production, your pending requests, your usage, and the sandbox playground for trying things. Settings (theme, density, language, accessibility, notifications) are under the same menu; they apply at once and travel with your account."),
              H1("7. Proposing an AI use for your team: the brief"),
              P("Build opens the intake brief: one page in six short sections, saved as you go. Fill it in the order it asks:"),
              steps(["<b>Use case.</b> A name, what happens today, the channel (your team, customers, partners, or a batch), and the team.",
                     "<b>People.</b> The business owner, the product owner, and the domain expert who will label examples, with the hours a week they can give.",
                     "<b>Data and tools.</b> The systems of record it reads, the tools it may call and their tiers, the data classes, and the ceiling on what it may do.",
                     "<b>Model.</b> What the model needs to be, the classification ceiling, and whether a substitute is acceptable.",
                     "<b>Outcome.</b> One metric, its unit, today's figure, the target, and when the baseline was measured.",
                     "<b>Review.</b> What happens next, acknowledged."]),
              P("The brief estimates the monthly model spend and the review hours as you fill it, and recommends a paved road. Filing it puts it in front of the platform lead; a brief that would let an AI change systems is filed by your team lead, and the form tells you so."),
              H1("8. For AI champions: the programme in one page"),
              P("One engineer per team, every two weeks, forty-five minutes: ten minutes of what shipped, one deep dive, and fifteen minutes on the collection. Each champion carries one initiative at a time, written as a brief, built from the collection on a paved road, and brought back as something everyone can reuse. Your first week: sign in, run one live example from the Tools tab, read one practice page in the knowledge base, and draft your brief."),
              P("The knowledge base holds the practices behind the components, the paved roads, the skills anyone can follow, and the programme's own pages; the Learn tab links to it."),
              H1("9. For owners and AI security engineers: signing a component off"),
              P("A building block reaches the shelf when two people have signed it at its current version: its <b>owner</b> (named on the component, signs by name) and an <b>AI security engineer</b> (signs by role). Signing means attesting four things on the form: you ran the tests and they are green, you ran the live example, you read the walkthrough end to end, and you read the rules it enforces and its known limits. The owner also names the project it was first used in for real."),
              shot("signoffs.png", "The sign-off queue under Build. The form opens in the row; the right column says what you may sign and how a recorded sign-off becomes a record."),
              P("The queue lists every component with its version and both sign-offs; the filter <b>Yours to sign</b> shows what waits on you. A sign-off recorded here is a request until an engineer applies it to the component and commits; the queue's download is that step. A new version of a component asks both people to sign again."),
              shot("onboarding.png", "The onboarding tracker: each component's stage on its way to the shelf, and the checklists for a new champion, an owner, and an AI security engineer."),
              H1("10. Getting help"),
              table([["Question", "Where"], ["I cannot see a service I need", "The request button on its card or page; your lead approves"], ["The assistant's answer looks wrong", "Answer the feedback question with no; open the cited page; use the handoff for a person"],
                     ["I want to propose something", "Build: start a brief; the platform lead reviews it"], ["I am a champion and stuck", "The champions channel and the office hour named in the hub's footer"],
                     ["A component I own needs a change", "Its owner page names the process; the technical guide has the details"], ["Something looks like a security problem", "The AI security engineers who sign components off; do not wait for the next meeting"]], widths=[62 * mm, 98 * mm])]


# =====================================================================================================================
# 2. The technical guide
# =====================================================================================================================

def technical(story):
    cover(story, "The Collection: technical guide", "The repository, the component contract, the services, the configuration for the bank's systems, deployment and operation.",
          "Engineers building with or contributing to the collection; platform and integration engineers deploying it; operators")
    story += [H1("1. What is in the repository"),
              table([["Path", "What it is"],
                     ["components/", "29 AI components in six categories under four groups (agents, python, typescript, skills). Each directory is self-contained: a manifest, a README, a walkthrough, a live example, tests"],
                     ["hub/", "The employee AI hub front end (React 18, TypeScript, Vite). Pixel-identical to its design artboards; a mock API for development; configured at runtime by hub-api"],
                     ["services/hub-api/", "The hub's API on the Python standard library: every path of the contract plus sign-offs, behind the bank's identity provider; serves the built hub"],
                     ["services/agent-runtime/", "One agent of the collection over MCP and a run API, wired to the bank's systems by configuration"],
                     ["tools/", "shelf.py (the manifest checker and exporter), publish_kb.py (pages into the knowledge base), new_component.py (the scaffold), kb-taxonomy.json"],
                     ["content/knowledgebase/", "Pages the collection authors for the knowledge base product (practices, paved roads, the programme, onboarding)"],
                     ["exports/knowledgebase/, SHELF.md, hub/src/api/mock/collection.ts, services/hub-api/data/collection.json", "Generated by tools/shelf.py --write; never edited by hand"],
                     ["config/, CONFIGURATION.md", "Every external system named once; what the bank supplies"],
                     ["deploy/, services/*/deploy/", "Compose for the sandbox; Dockerfiles, fail-closed entrypoints, ECS task definitions, task roles"],
                     ["scripts/", "verify.sh (every gate), bundle.sh (the offline release), smoke-container-tree.sh"],
                     ["PRODUCTION-READINESS.md, RUNBOOK.md, SECURITY.md, HANDOVER.md, CONTRIBUTING.md", "The operating pages and the contract"]], widths=[52 * mm, 108 * mm]),
              H1("2. Components: the contract"),
              P("A component is one directory with a <b>component.json</b> manifest. The shelf tool validates every manifest, checks that vendored copies are byte-identical to their source, checks tags against the knowledge base's taxonomy, runs every test and live example, and regenerates the exports. CI fails on any drift."),
              H2("2.1 Categories"),
              table([["Category", "What it is", "Who uses it", "What it must contain"],
                     ["agent", "An AI agent", "Operators; engineers deploy one", "A template (role, stages, tools by tier, a never list), the tools it may call, the harness it runs inside, declared in the manifest's agent block"],
                     ["harness", "The loop an agent runs inside", "Engineers building an agent", "Fixed hooks, action tiers, budgets, kill switches, a chained record"],
                     ["tool", "Code with one clear surface", "Engineers; an agent calls one through its harness", "The code and a test that proves it"],
                     ["integration", "A client for an external system", "Engineers connecting a system", "The client and an in-memory fake behind the same methods"],
                     ["pattern", "A reference implementation of a practice", "Engineers adopting the practice", "The implementation and its practice page"],
                     ["skill", "A procedure", "Anyone, nothing to run", "SKILL.md with the procedure and its checks, a template, a filled example"]], widths=[20 * mm, 34 * mm, 36 * mm, 70 * mm]),
              H2("2.2 The manifest"),
              P("Fields: name, version (semantic; sign-offs bind to it), category, agent (agents only), signoff (owner and ai_security, each null or by/date/version), used_in, language, summary (under 160 characters), status (ready, draft, deprecated), source (project, path, snapshot), owner (a handle), tags (from the taxonomy), spec (the platform design specification sections and PLT ids implemented in interim form, and the replacement test), requires, pairs_with, test, walkthrough, example (path and run), vendored (path and from)."),
              H2("2.3 Rules"),
              bullets(["Python components use the standard library only unless requires says otherwise; a component imports nothing outside its directory; shared files are vendored and declared.",
                       "Every component carries a version, two sign-offs, a walkthrough and a live example; the hub lists it as generally available only when both sign-offs name the current version.",
                       "Fakes ship with the real thing: an integration has an in-memory fake behind the same methods.",
                       "No secrets, no real ids; credentials are names looked up at call time.",
                       "A change a consumer would notice bumps the version, which makes both sign-offs stale."]),
              H2("2.4 The six stages to the shelf"),
              table([["Stage", "What proves it"], ["1 scaffolded", "The scaffold made the directory: version 0.1.0, sign-offs pending, a spec entry, a tag"], ["2 built", "README, walkthrough, example and tests filled and green; status ready"],
                     ["3 used once for real", "used_in names a project (the owner records it on the sign-off form)"], ["4 owner signed", "At this version, after running the tests and the example"], ["5 AI security signed", "At this version, after reading the rules and the walkthrough and running the example"],
                     ["6 on the shelf", "Both at the current version: generally available on the hub and in the knowledge base"]], widths=[38 * mm, 122 * mm]),
              H2("2.5 Signing off"),
              P("On the hub: Build, Sign-offs, or the card on the component's page. The server requires every attestation and the first real use; the owner signs by name (the manifest's owner is their handle) and AI security by the ai.security role. The manifest is the record and the commit is the signature:"),
              P("python3 tools/shelf.py --apply-signoffs shelf-signoffs.json&nbsp;&nbsp;# re-runs the tests, writes signoff.&lt;role&gt;<br/>python3 tools/shelf.py --write<br/>git commit -am \"Sign off &lt;component&gt; &lt;version&gt;\"", "code"),
              H2("2.6 Adding a component"),
              P("python3 tools/new_component.py python my-tool --category tool --summary \"What it does\"<br/>python3 tools/new_component.py agents my-agent --category agent --summary \"...\"&nbsp;&nbsp;# TEMPLATE.md first, then one test per never line<br/>python3 tools/shelf.py --write &amp;&amp; python3 tools/shelf.py --test --only python &amp;&amp; python3 tools/shelf.py --examples --only python", "code"),
              H1("3. The harness and the agent"),
              P("<b>governed-action-loop</b> is the harness: three fixed hooks on every call (before, after, record), action tiers R, W1, W2 and MONEY, a W1 call parked until the acting person confirms its exact hash, W2 under dual control, a taint ceiling that caps a tainted session at reads, kill switches, budgets, and a hash-chained record. It ships with a fake identity provider, a local signing key and a fake gateway, and with their production counterparts behind the same interfaces: <b>JwksIdP</b> (the bank's RS256 tokens through its JWKS, directory groups to roles) and <b>KmsKey</b> (catalog signing on an asymmetric KMS key through SigV4 from the task role)."),
              P("<b>incident-first-read-agent</b> is the reference agent. Its TEMPLATE.md is loaded as data and the harness's signed catalog is built from its tools, so the agent can call exactly what the template lists. It reads a ticket and the last deploy, produces a cited first read through the <b>cited-llm-engine</b> (rules offline, a model online; fenced sources, cite-or-drop, a proposal refused on taint), and parks the W1 comment. One test exists per line of its never list."),
              H1("4. MCP"),
              bullets(["<b>mcp-tool-server</b> (harness): JSON-RPC over stdio or Streamable HTTP in front of the loop. tools/list is the signed catalog with annotations derived from it; every tools/call runs the hooks; W1 is an elicitation; taint, ladder, scope and kill switches are 403 with WWW-Authenticate insufficient_scope; RFC 9728 metadata; sampling disabled.",
                       "<b>mcp-gateway-client</b> (integration): the harness's gateway for an external MCP server under a contract record: an allowlist pinned to description hashes, quarantine on any drift or on a description that scores as an injection, the credential a name.",
                       "<b>shelf-mcp-server</b> (tool): read-only tools and every README, walkthrough and template as resources, so a coding assistant discovers the collection without cloning it. One line registers it with Claude Code."]),
              H1("5. The services"),
              H2("5.1 hub-api"),
              table([["Area", "Behaviour"], ["Identity", "HUB_AUTH=oidc: RS256 through the JWKS (signature, exp, nbf, iss, aud), claims mapped by identity-map.json (group ids to roles, entitlements, teams, ladder). HUB_AUTH=mock: personas for development, refused in production"],
                     ["Catalog", "The bank's listings from HUB_CONSUMERS_FILE plus every component from collection.json; access resolved per person from entitlements"],
                     ["Briefs, requests, workspace, preferences", "The browser's rules mirrored server-side; etags with If-Match; the lead rule for write profiles; persisted per person"],
                     ["Conversations", "SSE view events from one of three assistants: fake, http (relay to the platform runtime, service credential by name), bedrock (sources from the knowledge base's search fenced by the guard, cite-or-drop, taint stops before the model)"],
                     ["The shelf", "Sign-offs recorded against the version signed at; owner by name, AI security by role; every attestation required; the export the shelf tool applies"],
                     ["Runtime configuration", "/config.js rendered from HUB_WEB_* so one built hub runs in every environment"],
                     ["Static, record, health", "The hub's dist served with an SPA fallback; SQLite at HUB_DB (a file in staging and production); /api/health anonymous; logs ids only; request bodies capped; SIGTERM finishes in-flight requests"]], widths=[40 * mm, 120 * mm]),
              H2("5.2 agent-runtime"),
              table([["Area", "Behaviour"], ["Surface", "/mcp (the template's tools; W1 as elicitation), /runs (a first read: read, think, propose, park), /runs/{session}/confirm (the person confirms the exact hash; runs once), /health"],
                     ["Identity", "AGENT_IDENTITY=oidc through the JWKS with groups to the operator and approver roles; fake in the sandbox"],
                     ["Signing", "AGENT_SIGNING=kms; local in the sandbox"], ["Think step", "AGENT_ENGINE=bedrock through the VPC endpoint with the template's role as the system prompt; rules in the sandbox"],
                     ["Targets", "AGENT_TARGETS names which of the template's targets are real: tickets is the Jira connector, deploys the Azure DevOps connector; the rest are fakes, refused in staging and production. The targets a template needs are read from the template"],
                     ["Record", "SQLite on a volume; verify-record at every start; export-audit puts the chain and a latest.json pointer to S3 with SigV4"]], widths=[40 * mm, 120 * mm]),
              H1("6. Configuring for the bank's systems"),
              P("Every variable is in <b>config/collection.env.example</b> and explained in <b>CONFIGURATION.md</b>. A variable ending in _NAME is the name of a secret in the secrets provider (HUB_SECRETS=aws is Secrets Manager reached with the task role; file: a mounted file; env only for a developer's shell). Each service's settings fail closed: check-config lists every problem by variable name, never a value, and the entrypoint runs it before the process listens."),
              table([["System", "Variables", "Needed from the bank"],
                     ["Identity provider", "HUB_IDP_ISSUER, HUB_IDP_AUDIENCE, HUB_WEB_OIDC_AUTHORITY, HUB_WEB_OIDC_CLIENT_ID, AGENT_IDP_*", "An app registration per deployable with the groups claim; the redirect URI"],
                     ["Groups to grants", "HUB_IDENTITY_MAP, HUB_AI_SECURITY_GROUP, AGENT_OPERATOR_GROUP_ID, AGENT_APPROVER_GROUP_ID", "Which groups grant which roles, entitlements, teams and ladders"],
                     ["Listings", "HUB_CONSUMERS_FILE", "The bank's own consumers and the registry of systems and tools"],
                     ["Record", "HUB_DB, AGENT_DB", "A persistent volume (EFS)"],
                     ["Model", "*_BEDROCK_*", "An inference profile approved by model risk; the VPC endpoint; bedrock:InvokeModel on the task role"],
                     ["Secrets", "*_SECRETS, the *_NAME variables", "Secrets under the service prefix; secretsmanager:GetSecretValue on the task role"],
                     ["Catalog signing", "AGENT_KMS_KEY_ID", "An asymmetric KMS key; kms:Sign and kms:GetPublicKey"],
                     ["Jira, Azure DevOps", "AGENT_JIRA_*, AGENT_DEPLOYS_*", "A service account with read on incident projects and comment; a PAT scoped to pipelines"],
                     ["Knowledge base", "HUB_KB_URL, HUB_KB_SEARCH_URL", "The console URL; its /search endpoint for citations"],
                     ["Audit export", "AGENT_AUDIT_EXPORT", "A bucket with KMS encryption and s3:PutObject on the task role"]], widths=[30 * mm, 66 * mm, 64 * mm]),
              P("Sandbox allows mock identity, the fake assistant, the rules engine, local signing and fake targets. Staging and production refuse all of them, require https public URLs, a file-backed record, a non-environment secrets provider, KMS signing and, for the agent, a real system for every target its template names. The same image runs in both; only the environment changes.", "callout"),
              H1("7. Deployment"),
              steps(["<b>Build the images</b> from the repository root with the base image digest pinned to the bank's approved image: docker build -f services/hub-api/deploy/Dockerfile and services/agent-runtime/deploy/Dockerfile. The hub's dist is prebuilt (the release bundle ships it) and needs no rebuild for a new environment.",
                     "<b>Mount the configuration</b>: identity-map.json and consumers.json on the hub's read-only config volume.",
                     "<b>Create the secrets</b> under hub/ and agents/, and the task roles from services/*/deploy/iam-task-role-policy.json.",
                     "<b>Register the task definitions</b> from services/*/deploy/ecs-task-definition.json with the record volumes on EFS.",
                     "<b>Verify</b>: /api/health and /health answer; a real bearer resolves to the expected principal; the record survives a task restart; the audit export lands in the bucket."]),
              P("Locally, with fakes and no account: docker compose -f deploy/compose.yaml up. Without a container daemon: scripts/smoke-container-tree.sh assembles each Dockerfile's COPY set, runs the entrypoint, checks health and that production refuses the tree's fakes."),
              H1("8. Verification, CI and the offline release"),
              P("scripts/verify.sh python&nbsp;&nbsp;&nbsp;# the shelf, the vendoring, every Python component and service, the refusals, the container trees<br/>scripts/verify.sh typescript<br/>scripts/verify.sh hub&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# typecheck, lint, 43 tests, build<br/>scripts/bundle.sh&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# release/collection-&lt;sha&gt;.tar.gz with the hub prebuilt and a sha256 manifest", "code"),
              P(".github/workflows/ci.yml and ci/azure-pipelines.yml both call verify.sh, so the two runners cannot drift. The bundle, unpacked in a clean directory, verifies its manifest and passes the Python gates with no network and no Node. Services vendor component files through services/vendor.json; python3 services/vendor.py --check refuses drift."),
              H1("9. Operating"),
              P("RUNBOOK.md covers health, what a refused start looks like, rolling out a build, applying a sign-off, changing listings or grants, stopping the agent, rotating a credential, exporting the chain, and what to do when the record does not verify (restore, compare with the last export, open an incident). SECURITY.md maps each threat to its control and its test."),
              H1("10. The knowledge base"),
              P("Pages under content/knowledgebase/ and the generated component pages obey the product's checks (frontmatter, under 200 lines, organisation-neutral, links inside docs/, list items on one line). Deliver with python3 tools/publish_kb.py &lt;checkout&gt;, then the product's kb-librarian index --write and check. The publisher is idempotent."),
              H1("11. Where the platform replaces the interim"),
              P("Every component's manifest names the platform design specification sections and PLT ids it implements in interim form and a replacement test: the condition the platform must pass before the component is retired. The hub shows both on each listing. The MCP tool server is the specification's R1 road with the harness behind the transport; the gateway client is the contract registry's rules for external servers; the harness's stores and gateway are the control layer's when it arrives.")]


# =====================================================================================================================
# 3. The leadership brief
# =====================================================================================================================

def brief(story):
    cover(story, "The AI Hub and the Collection: leadership brief", "What was built, why it matters, what it costs, what is governed, and what is needed to deploy it into the bank.",
          "Leadership; the platform, security and model-risk leads; the sponsors of the AI champions programme")
    story += [H1("1. In one paragraph"),
              P("Two internal products, the first responder and the knowledge base, produced working AI controls, connectors and habits that every team building with AI needs. The Collection is how they spread: 29 self-contained building blocks in six categories, each versioned, tested, walked through and signed off by its owner and an AI security engineer, listed on the employee AI hub and published into the knowledge base. Around it, an AI champions programme (one engineer per team, every two weeks) turns those blocks into the team's own initiatives on approved paved roads. The hub, its API and an agent runtime are implemented and packaged to run inside the bank against its identity provider, model service, secrets, ticketing and deployment systems, with nothing fetched from the public internet."),
              H1("2. What is delivered"),
              table([["Deliverable", "State"],
                     ["29 components: 1 agent, 2 harnesses, 9 tools, 7 integrations, 3 patterns, 7 skills", "Every test suite and live example green; each traced to the platform design specification with a replacement test"],
                     ["The employee AI hub", "Pixel-identical to its design; configured at runtime; self-hosted assets; 43 tests and a pixel guard at zero"],
                     ["The hub's API behind the bank's identity provider", "Implemented on the standard library; 17 tests including the OIDC path and the assistant backends; a browser flow proven end to end"],
                     ["An agent runtime", "The incident first-read agent over MCP and a run API, wired to Jira, Azure DevOps, Bedrock, KMS and the identity provider by configuration"],
                     ["Governance surfaces", "Sign-off queue and form, onboarding tracker, categories; the manifest is the record and the commit the signature"],
                     ["Packaging", "Containers with fail-closed entrypoints, ECS task definitions, least-privilege roles; an offline release bundle; one verify script for GitHub and Azure Pipelines"],
                     ["Operating pages", "Production readiness, runbook, security notes, handover, configuration guide, contributing contract; a user manual and a technical guide"]], widths=[70 * mm, 90 * mm]),
              H1("3. Why it matters"),
              bullets(["<b>Speed with control.</b> A team starts from a signed block with a five-minute README instead of from a blank page, and every block enforces the same rules: a model only cites, a write waits for a person, a tainted input caps the session at reads, nothing holds a credential.",
                       "<b>One front door.</b> Employees see what they may use and ask for the rest; leaders see what is in flight and where each initiative stands.",
                       "<b>A path to the platform.</b> Each block names what in the platform design replaces it and the test that proves the replacement; the work is not throwaway and not a second platform.",
                       "<b>People, not just software.</b> The champions programme, the sign-off roles and the onboarding stages make adoption a practice with names on it."]),
              H1("4. What it costs to run"),
              table([["Item", "Driver", "Note"],
                     ["Compute", "Two small containers (hub, agent) on Fargate, a record volume each", "Standard library only; no licence; no third-party service"],
                     ["Model usage", "Assistant turns and agent first reads on Bedrock", "Budgets per session are enforced; the hub shows usage back; charge-back per cost centre is in the design"],
                     ["People", "The enablement lead; two to four hours a week per champion; AI security engineers' review time", "Two AI security engineers at minimum so no component waits on one person"],
                     ["Platform", "Identity registrations, secrets, a KMS key, an inference profile, a bucket", "One-time setup, named in the readiness page"]], widths=[26 * mm, 74 * mm, 60 * mm]),
              H1("5. How it is governed"),
              P("Two sign-offs at every version, attested on a form the server enforces; fakes that cannot reach production; credentials never held; a hash-chained record verified at every start and exported nightly; logs that carry identifiers only; a threat model mapped to tests. Model risk gets the engine, stage and token counts on the chain and a feedback question on every answer. The categories say what a thing is and who may use it: a skill anyone, an agent only through its harness."),
              H1("6. What is open, and who owns it"),
              table([["Open item", "Owner"], ["Group ids, app registrations, the groups claim on tokens", "Identity engineer"], ["Secrets, the KMS key, the inference profile, the bucket, the task roles applied", "Integrations engineer, platform team"],
                     ["The model approved and the first-read judge validated", "Model risk"], ["The base image pinned and images built in the bank's registry", "Integrations engineer"],
                     ["The bank's own listings and the identity map filled in", "Platform team"], ["The first real use of each component and the sign-offs themselves", "Component owners, AI security engineers"],
                     ["The pages published into the bank's knowledge base", "Enablement lead"], ["The MCP conformance suite run with a reviewed expected-failures file", "Platform team"]], widths=[110 * mm, 50 * mm]),
              P("None of these is a design gap: each is an account, an id, a key or a person. When they are closed, deployment is a configuration change on the build that already passed every gate.", "callout"),
              H1("7. Decisions needed"),
              steps(["Name the two AI security engineers and the enablement lead.",
                     "Approve the first production increment: the hub in staging with the platform runtime's assistant (or none), and the agent reading real systems and writing to none.",
                     "Approve the inference profile with model risk and the charge-back rule for model usage.",
                     "Confirm the champions programme's cadence and the first cohort, one engineer per team."]),
              H1("8. The next ninety days"),
              bullets(["Weeks 1 to 3: the open items closed; staging deployment; the first components used once for real and signed.",
                       "Weeks 4 to 8: the first cohort's briefs filed; two initiatives built on paved roads from the collection; the first agent reading real incidents in staging.",
                       "Weeks 9 to 13: production for the hub and the read-only agent; the first write increment gated by its demonstration; the readiness page re-baselined with measured numbers."])]


if __name__ == "__main__":
    for f, t, fn in [("user-manual.pdf", "The AI Hub and the Collection: user manual", manual), ("technical-guide.pdf", "The Collection: technical guide", technical), ("leadership-brief.pdf", "The AI Hub and the Collection: leadership brief", brief)]:
        print("wrote", build(f, t, fn))
