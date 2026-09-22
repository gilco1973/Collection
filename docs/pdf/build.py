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


import sys as _sys
_sys.path.insert(0, HERE)
import diagrams as D


def fig(drawing, caption, scale=0.92):
    d = drawing
    d.scale(scale, scale); d.width *= scale; d.height *= scale; d.hAlign = "CENTER"
    return KeepTogether([d, Spacer(1, 2), P(caption, "small"), Spacer(1, 8)])


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
# 1. The user manual (for people who use the hub, and for champions)
# =====================================================================================================================

def manual(story):
    cover(story, "The AI Hub and the Collection", "A short manual for the people who use the hub, and for the engineers who join the AI champions programme.",
          "Everyone who signs in to the hub; AI champions; component owners; AI security engineers")
    story += [H1("Before you start"),
              P("You don't need to know how any of this works to use it. If you can sign in to a company website and use a search box, you can use the hub. "
                "This manual goes through the screens in the order you'll meet them, and then covers the two things that involve more than just using it: proposing an AI use for your team, and signing off a building block if you happen to own one or review them for security."),
              P("A word on what the hub is not. It is not a chatbot that can do things to your accounts or your systems. The assistant reads pages and tells you what they say, with the page cited. "
                "The agents can read tickets and deploy histories and draft things, but nothing they draft is posted or changed anywhere until a named person says yes. We built it that way on purpose, and the rest of this manual will show you where you can see that for yourself."),
              H1("1. Signing in"),
              P("Open the hub's address in your browser and sign in with the account you use for everything else. The hub never sees your password; the company's identity provider handles that and just tells the hub who you are and which groups you're in. "
                "What you see next depends on those groups. If something you expected is missing, that's not a fault. It's access, and there's a button on every card and page to ask for it."),
              H1("2. The guide"),
              P("Bottom right of every page there's a small button with a spark on it. That's the guide, and it's the fastest way to learn the hub. Open it once and it asks what you're here for: to build something, to understand and decide, or just to use the hub. Pick one; it suggests from your role, and you can change it any time from the top of the panel."),
              P("From then on the panel keeps to what matters for you. It tells you in a line what the page you're on is for. It suggests one next step, and only one, worked out from what you've actually done: a brief you left half-finished, components waiting on your signature, a page you haven't opened yet. It shows your path, a short list of steps that tick themselves off as you go, and a <b>Show me around</b> button that walks you through the pages with the relevant part of each one lit up. And you can ask it questions."),
              shot("guide.png", "The guide, open on an agent's listing for someone who chose 'understand and decide': where you are, one next step, the path, and a place to ask."),
              P("The answers are worth a word. The guide doesn't make things up about the platform. It reads our own documentation, quotes the passages that answer your question, and names the page each one came from, so you can go and read the rest. If the pages don't cover something, it says so rather than guessing. If a question looks like an instruction rather than a question, it declines. It has no tools and cannot act for you: it points, it explains, it never changes anything.", "callout"),
              P("If you're a leader reading this, the guide is where to start. Choose <b>understand and decide</b>. On an agent's page it will tell you that the permission table you're looking at is the whole list and nothing outside it can run; on the sign-off page, who signs and what they attest; in your workspace, what it costs. Ask it plainly what an agent cannot do."),
              H1("3. Discover"),
              P("Discover is the catalog. The row at the top is what's already open to you. Below it, tabs sort everything else into assistants, agents, knowledge, tools, and the paved roads (the approved ways to build something new). The search box at the top finds any of them, and pressing Ctrl+K anywhere opens it."),
              shot("discover.png", "Discover with the Agents tab open. Each card names the service, which road it runs on, whether it is generally available or still a preview, and how you reach it."),
              P("Each card says one of four things about access. <b>Open</b> means click it and go. <b>Request access</b> sends a request to your lead with one click; if you already have it, or already asked, the hub says so (<b>Already yours</b>, <b>Already asked</b>) and sends nothing twice. <b>View</b> means you can read about it but your role doesn't use it. <b>Contract</b> means another team runs it and the page says who to ask."),
              H1("4. A listing page"),
              P("Everything in the catalog has a page, and they all follow the same layout, so once you've read one you can read them all. Top to bottom: what it does; what it can read and do, each operation with its tier; the evidence behind it; the owner and how to get support; and the versions. "
                "The tier is worth a second look. <b>R</b> means read only. <b>W1</b> means it can write something, but only after the person using it confirms that exact action. <b>W2</b> means a second person has to approve. Anything involving money is simply not allowed."),
              shot("listing.png", "A listing page. On the right: the sign-off card, the getting-started steps, the owner and the versions."),
              P("The chips under the title say at a glance which road it's on, what language it's written in, whether it's ready, and which parts of the platform design it implements. If both its owner and an AI security engineer have signed it, it says <b>signed</b>. If not, the hub calls it a preview, and you should treat it as one."),
              H1("5. Asking the assistant"),
              P("Open the assistant from Discover or from your workspace and type your question the way you'd ask a colleague. Three things are worth knowing about the answer you get back."),
              P("It cites its sources. Claims are marked in the text and the pages they came from are listed underneath, with their classification. A claim with no source is shown as unsupported, and you should read it as a hint rather than a fact. "
                "It shows its work. When it looks something up, that step appears in the conversation with what it searched for, so you can see what it did and not just what it said. "
                "And it asks one question at the end: did this answer yours? Please answer it. That one click is how we measure whether the thing is any good. If you'd rather talk to a person, the handoff button routes the conversation to one. "
                "If something stops the conversation, the banner shows the platform's own sentence first, such as <b>This conversation has reached 200 turns; start a new conversation</b> or <b>Your role no longer opens this assistant</b>, so you know what to do without asking anyone."),
              fig(D.assistant(), "How an answer is produced. The knowledge base is searched, the pages that match are fenced off as sources, the model answers only from those, and every claim is either cited or dropped."),
              P("Now and then the assistant will tell you that a page looked like an instruction rather than evidence, and that it didn't use it. That's the protection doing its job: something in a page or a ticket was trying to steer it. Rephrase your question, or open the page directly.", "callout"),
              H1("6. Your workspace"),
              P("My workspace gathers what's yours: the assistants you use, your team's services and how far along each one is, your pending requests, your usage, and a sandbox playground for trying things. Settings are under the same menu (theme, density, language, accessibility, notifications). They apply straight away and follow your account."),
              H1("7. Proposing an AI use for your team"),
              P("The Build tab opens the intake brief. It's one page in six short sections and it saves as you go, so you can come back to it. A brief names the team that owns it, so if the platform lists you in no team yet the page says so and asks you to have your lead add you before you start. It asks, in order: what the use case is and what happens today; who the business owner, product owner and domain expert are; which systems and tools it needs and what tier they'd run at; what kind of model it needs; one measurable outcome with today's figure and a target; and finally that you've read what happens next."),
              P("The third section is where you build from what already exists. Press <b>Browse the catalog</b> and a composer opens: on the left, everything the bank has (the systems of record, the tools each one offers with their tier, the collection's components, and the services already on the platform); on the right, your brief. Drag anything from the left onto the right, or press Add. A tool brings its system with it. Under the brief, the composer tells you what your choices mean as you make them: the highest tier so far and whether your ceiling covers it, the data classes the tools read, how many tools you have left under the session limit, and whether a lead will have to file the brief. One button fixes each of those, except restricted data: a tool that reads restricted data is named as one a first consumer cannot use, and the only ways forward are to remove it or take the use case to the platform team for a data-class exception. A system without a recorded contract is shown greyed with the reason, and a money tool is refused for a first consumer."),
              P("One thing you do not have to remember: the harness. The moment your brief names a tool, the composer shows five components locked under <b>Required with any tool</b>: the governed action loop, the untrusted input guard, the cited LLM engine, the audit chain and ids-only logging. That is the set every solution that calls a tool runs inside, and it is written into the brief when you file it, by the hub and again by the platform, so it cannot be left out or taken out. The review page names it as the brief's harness.", "callout"),
              shot("composer.png", "The composer, open from section 3. A tool has just been dropped onto the brief and brought its system with it; the panel below says what the choices mean and offers the fix."),
              P("As you fill it in, the brief estimates the monthly model spend and the review effort, and suggests which paved road fits. When you file it, the platform lead sees it. If what you're proposing would let an AI change a system rather than just read one, your team lead has to be the one to file it, and the form will tell you so."),
              H1("8. If you're an AI champion"),
              P("Champions are engineers, one per team, and you don't need to have built anything with AI before. The programme is a forty-five minute meeting every two weeks: ten minutes on what shipped, twenty on one deep dive, fifteen on the collection. You carry one initiative at a time. It starts as a brief, gets built from the collection on a paved road, and comes back as something the next team can reuse."),
              P("Your first week is small on purpose. Sign in to the hub. Run one live example from the Tools tab in a terminal and watch what it prints. Read one practice page in the knowledge base (the Learn tab links there). Then draft your brief and bring it to the next meeting. The technical guide is the next thing to read after that; it starts from the basics."),
              H1("9. If you sign components off"),
              P("A building block only reaches the shelf when two people have signed it at its current version. Its <b>owner</b>, who is named on it, signs by name. An <b>AI security engineer</b> signs by role. Both of you attest to four things on the form: you ran the tests and they were green, you ran the live example, you read the walkthrough all the way through, and you read the rules it enforces and its known limits. The owner also names the project it was first used in for real."),
              shot("signoffs.png", "The sign-off queue under Build. The form opens in the row. The right column tells you what you may sign and what happens after you do."),
              P("The queue lists every component with its version and both sign-offs, and the <b>Yours to sign</b> filter shows what's waiting on you. A sign-off you record here is a request until an engineer applies it to the component and commits it; the download button on the page is that step, and the commit is what makes it a record. If a component gets a new version, both of you are asked again."),
              fig(D.signoff(), "A component's way to the shelf, and how a sign-off on the hub becomes a record in the repository."),
              shot("onboarding.png", "The onboarding tracker shows where every component is and what has to happen next, plus the checklists for a new champion, an owner and an AI security engineer."),
              H1("10. Getting help"),
              table([["If", "Then"], ["You can't see a service you need", "Use the request button on its card or page; your lead approves it"], ["An answer looks wrong", "Answer the feedback question with no, open the cited page, or use the handoff to reach a person"],
                     ["You don't know where to start", "Open the guide (bottom right, or Alt+G) and tell it what you're here for"], ["You want to propose something", "Build, then start a brief"], ["You're a champion and stuck", "The champions channel, or the office hour named in the hub's footer"],
                     ["Something looks like a security problem", "Tell the AI security engineers straight away. Don't wait for the next meeting"]], widths=[62 * mm, 98 * mm])]


# =====================================================================================================================
# 2. The technical guide (for engineers, starting from the basics)
# =====================================================================================================================

def technical(story):
    cover(story, "The Collection: technical guide", "For engineers who build with the collection, contribute to it, or run it. It starts from the basics and ends at deployment.",
          "AI champions and other engineers; platform and integration engineers; operators")
    story += [H1("1. The basics, if you're new to this"),
              P("A language model is a function from text to text. You give it a prompt, it gives you a continuation. It has no memory between calls, no access to anything you don't put in the prompt, and no way to act on the world. Everything interesting, and everything risky, comes from what we wrap around it."),
              P("An <b>assistant</b> is a model wrapped in a loop that fetches relevant pages, puts them in the prompt, and shows the answer. It reads, it doesn't act. An <b>agent</b> is a model wrapped in a loop that can also call tools: read a ticket, look up a deploy, post a comment. The moment a model can call tools, the question that matters is not how clever the model is but what the loop lets it do, and who has to say yes first."),
              P("That loop is what we call the <b>harness</b>. It's ordinary code, it runs the same way every time, and the model cannot change it. When people in this repository say an agent is safe to run, they mean the harness is, and they can point at the test that proves each rule. Keep that distinction in mind and the rest of this guide will read easily."),
              P("One more term. <b>Prompt injection</b> is when text the model reads (a ticket, a web page, a tool description) contains instructions, and the model follows them as if they came from you. The defence here is simple to state: text the model reads is evidence, never instruction. Sources are fenced off, scored, and if one looks like an instruction the session is marked tainted and can only read from then on.", "callout"),
              H1("2. What's in the repository"),
              P("One repository, four parts. <b>components/</b> is the shelf: 29 building blocks, each in its own directory with a manifest, a README that gets you running in five minutes, a step-by-step walkthrough, a live example and tests. <b>hub/</b> is the employee AI hub front end. <b>services/</b> holds the two things we deploy: hub-api, the hub's back end, and agent-runtime, which runs one agent. <b>tools/</b> holds the shelf tool that checks every manifest and generates the hub's listings and the knowledge base's pages. The knowledge base itself is a separate product; we publish pages into it."),
              fig(D.architecture(), "Where each piece runs inside the bank and what it talks to. The two services are one container each with a record file on a volume."),
              H1("3. The shelf: what a component is"),
              P("Every component declares a <b>category</b>, and the category tells you who it's for and what it has to contain. A <b>skill</b> is a written procedure with a template and a filled example; anyone can follow it and there's nothing to run. A <b>tool</b> is code with one clear surface and a test. An <b>integration</b> is a client for an external system that ships with an in-memory fake behind the same methods, so you can test without an account. A <b>pattern</b> is a small reference implementation of a practice. A <b>harness</b> is the loop an agent runs inside. An <b>agent</b> is the composite: a template that says what it is and what it may call, the tools it calls, and the harness it runs in."),
              P("The manifest, component.json, carries the version, the two sign-off slots, where it was lifted from, its tags, the test command, the walkthrough and example paths, any files vendored from another component, and which sections of the platform design specification it implements in the meantime, with the test the platform has to pass before the component can be retired. The shelf tool checks all of it on every commit."),
              H2("The rules you'll bump into"),
              P("Python components use the standard library only, unless the manifest says otherwise. A component imports nothing outside its own directory; when two need the same file, one owns it and the other vendors a byte-identical copy and declares it. Credentials are names looked up at call time, never values. And any change a consumer would notice bumps the version, which makes both sign-offs stale until they're given again."),
              H2("Adding one"),
              P("python3 tools/new_component.py python my-tool --category tool --summary \"What it does\"<br/>python3 tools/new_component.py agents my-agent --category agent --summary \"...\"<br/>python3 tools/shelf.py --write &amp;&amp; python3 tools/shelf.py --test --only python", "code"),
              P("For an agent, write TEMPLATE.md first and then one test per line of its never list; the incident first-read agent is the model to copy. When the tests are green and it has run once for real, the owner and an AI security engineer sign it on the hub, an engineer applies the export with python3 tools/shelf.py --apply-signoffs and commits, and the commit is the signature."),
              fig(D.signoff(), "The six stages, each read from the manifest rather than guessed, and the path from the form on the hub to the commit."),
              H1("4. How an agent runs"),
              P("The <b>governed-action-loop</b> component is the harness. Every call an agent makes goes through three hooks in a fixed order, and there is no way to reach a target around them."),
              fig(D.harness(), "One call through the loop."),
              P("Before the call, the harness checks for a kill switch, checks the tool is in the signed catalog, validates the arguments, and asks the policy bundle. A read runs. A write (W1) is parked with a hash of the exact tool and arguments until the acting person confirms it; the confirmation is consumed once, so a replay fails. A bigger change (W2) needs another person's approval reference. Money is forbidden outright. After the call, the result is projected to the shape the catalog declared, masked for personal data, and scored; if it scores as an injection the session is tainted and capped at reads. And every call, decision, confirmation and stop is written to a hash-chained record you can verify."),
              P("The <b>incident-first-read-agent</b> is the reference. Its TEMPLATE.md is data: the role, the stages, the tools with their tiers and result shapes, a budget, and a list of things it never does. The code builds the harness's signed catalog from that list, so the agent can call exactly what the template names and nothing else. Its tests include one per line of the never list. Run python3 example.py in its directory to watch a clean incident and then a poisoned one."),
              H1("5. MCP, in one paragraph each"),
              P("MCP is the protocol AI clients use to call tools. Three components speak it. <b>mcp-tool-server</b> puts the harness behind an MCP transport: the tool list is the signed catalog, every call runs the hooks, a W1 call becomes an elicitation the client puts to the person, and a tainted or out-of-scope call is a 403 that names the scope. <b>mcp-gateway-client</b> is the other direction: the harness calling someone else's MCP server under a contract record, with the tool descriptions pinned and any drift quarantining the server. <b>shelf-mcp-server</b> is read-only and lets a coding assistant such as Claude Code browse the shelf without cloning it."),
              H1("6. The services"),
              P("<b>hub-api</b> implements the hub's whole API on the Python standard library. It verifies the bank's RS256 tokens against the identity provider's key set, maps directory groups to roles and entitlements with a file the platform team owns, serves the catalog from the bank's own listings plus the shelf's components, keeps briefs, requests and sign-offs in a SQLite record, and streams assistant turns from one of three back ends: a fake for development, a relay to the platform runtime, or Bedrock with the knowledge base's search for sources. It also serves the built hub itself and a small config.js the page reads at start, so the hub is built once and configured per environment."),
              P("The hub's guide is part of hub-api too. tools/shelf.py --write splits the repository's pages (the root pages, the knowledge-base pages and every component README) into a corpus of a few hundred passages, each tagged with the audience it was written for. POST /guide/ask screens the question for instructions with the harness's guard, ranks the passages with BM25 and a small table of plain-language synonyms, and answers either with the passages themselves, attributed, or, when HUB_ASSISTANT is bedrock, with a cite-or-drop answer from the model over those passages only. The hub's in-browser mock ranks the same corpus the same way, so the guide works in the sandbox without a service."),
              P("<b>agent-runtime</b> serves one agent of the collection over MCP and a small run API. Everything that touches a bank system is chosen by configuration: the identity provider or a fake, a KMS key or a local one, Bedrock or the offline rules engine, the Jira and Azure DevOps connectors or their fakes. Staging and production refuse every fake and require a real system for every target the agent's template names. The record is verified at every start and exported to S3."),
              H1("7. Configuring it for the bank"),
              P("Every variable is in config/collection.env.example, and CONFIGURATION.md explains what the bank has to supply for each system. Two conventions carry most of the weight. A variable ending in _NAME is the name of a secret in the secrets provider, never a value; the task role's SigV4 credentials fetch it at call time. And every service's settings fail closed: check-config lists each problem by variable name and exits, and the container's entrypoint runs it before the process listens. The same image runs in the sandbox with fakes and in production against the bank; only the environment changes."),
              table([["System", "What the bank supplies"],
                     ["Identity provider", "An app registration per deployable with the groups claim on tokens; the group ids for the identity map; the redirect URI"],
                     ["Model", "An inference profile approved by model risk; the VPC endpoint; InvokeModel on the task role"],
                     ["Secrets and keys", "Secrets under the service prefix; an asymmetric KMS key for catalog signing"],
                     ["Jira, Azure DevOps", "A service account with read on incident projects and comment; a PAT scoped to pipelines"],
                     ["Knowledge base", "The console URL and its /search endpoint"],
                     ["Storage", "An EFS volume for each record; a KMS-encrypted bucket for the audit export"]], widths=[40 * mm, 120 * mm]),
              H1("8. Deploying it"),
              P("Build the two images from the repository root with the base image digest pinned to the bank's approved one; the hub's dist is prebuilt and needs no rebuild for a new environment. Mount identity-map.json and consumers.json on the hub's config volume, create the secrets, apply the task roles from services/*/deploy/iam-task-role-policy.json, register the task definitions, and check /api/health and /health. Locally, docker compose -f deploy/compose.yaml up runs both with fakes; without a container daemon, scripts/smoke-container-tree.sh assembles each Dockerfile's copy set and starts it."),
              P("scripts/verify.sh python&nbsp;&nbsp;&nbsp;# the shelf, the vendoring, every Python component and service, the refusals, the container trees<br/>scripts/verify.sh hub&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# typecheck, lint, tests, build<br/>scripts/bundle.sh&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# the offline release with the hub prebuilt and a sha256 manifest", "code"),
              P("Both CI definitions, GitHub Actions and Azure Pipelines, call the same verify script. The bundle unpacked in a clean directory passes every Python gate with no network and no Node."),
              H1("9. Running it"),
              P("RUNBOOK.md is the page to have open. It covers what a refused start looks like, rolling out a build, applying a sign-off, changing listings or grants, stopping the agent, rotating a credential, and exporting the chain. One rule from it is worth repeating here: if the record doesn't verify, don't repair rows. Restore the volume, compare the chain's head with the last export, and open an incident. SECURITY.md maps each threat to the control and the test that covers it."),
              P("Day to day, four things matter. The load balancer watches /api/ready and /ready, which say whether a task should get traffic and name the check that fails. Every response carries a request id the person can quote and the logs carry on every line. Each person has a per-minute limit, so a runaway client gets a 429 and nobody else notices. And the record is versioned and backed up online: a backup command copies it while serving, a record from a newer build refuses to open under an older one, replays and old conversations are pruned on a schedule, and the agent's chain leaves the task on an interval you set."),
              H1("10. Where the platform takes over"),
              P("None of this is meant to outlive the platform. Each component's manifest names the sections of the platform design specification it implements in the meantime and a replacement test: the condition the platform has to meet before the component is retired. The MCP tool server is the specification's R1 road with the harness behind the transport; the gateway client is its contract-registry rules; the harness's stores and gateway are placeholders for the control layer. When those arrive, the tests are the handover.")]


# =====================================================================================================================
# 3. The leadership brief
# =====================================================================================================================

def brief(story):
    cover(story, "The AI Hub and the Collection", "A brief for leadership: what we built, what it can and cannot do, what it costs, and what we need from you.",
          "Leadership; the platform, security and model-risk leads; the sponsors of the AI champions programme")
    story += [H1("The short version"),
              P("We took the working parts out of two internal AI projects, the first responder and the knowledge base, and turned them into a shelf of building blocks that any team can reuse: 29 of them, each tested, versioned and signed off by two people before it counts as ready. We put an employee AI hub in front of the shelf, implemented the hub's back end and an agent runtime so the whole thing runs inside the bank against our own identity provider, model service, secrets, Jira and Azure DevOps, and packaged it so it can be delivered without touching the public internet. Around it there's a programme, one engineer per team every two weeks, to turn the blocks into each team's own initiatives."),
              P("If you take one thing from this brief, take this: the agents in here can read, and they can draft, but they cannot change anything until a named person says yes to that exact change. That is not a policy we ask people to follow. It is how the code is built, and we can show you the tests."),
              H1("The question you're probably asking"),
              P("Most people's worry about AI agents is the right one: what stops it doing something we didn't ask for? Here is our answer, in the order the code enforces it."),
              P("An agent can only call the tools written in its template, and that list is signed. Every call goes through the same three checks, and the model cannot skip them. Reading is allowed. Writing is parked until the person who is using the agent confirms that exact action, once; a second confirmation of the same thing is refused. Anything bigger needs a second person. Anything involving money is refused outright. If the text the agent reads contains instructions, say a ticket someone has doctored, the session is marked and from then on it can only read. There is a kill switch. And every step is written to a record that cannot be edited without the edit showing."),
              fig(D.harness(), "One call through the loop. The three hooks are ordinary code that runs the same way every time."),
              P("The employee assistant is simpler still. It reads pages from the knowledge base and tells you what they say, with the page cited. It has no tools. A claim it cannot back with a page is dropped or shown as unsupported.", "callout"),
              P("You can check all of this yourself without reading a line of code. Open the hub, press the guide button at the bottom right, and choose <i>understand and decide</i>. It walks you through the pages a leader needs, and answers questions like the one above by quoting our own documentation and naming the page. It has no tools either."),
              H1("What we've actually delivered"),
              P("Twenty-nine components in six categories, every test and live example passing, each traced to the platform design specification with a test that says when the platform can replace it. The hub, pixel-identical to its design, with the sign-off queue, the onboarding tracker and a guide that walks each kind of person through it added. The hub's API and an agent runtime, both on the Python standard library with no third-party dependency, both refusing to start in production with any fake left in. Containers, task definitions and least-privilege roles with placeholders where the bank's identifiers go. An offline release bundle that verifies itself. A user manual, a technical guide, a runbook, a security page and a readiness page."),
              fig(D.architecture(), "How it sits inside the bank. Nothing on this diagram reaches the public internet; the hub's own fonts and scripts are served from inside."),
              H1("What it costs"),
              P("Two small containers and a storage volume each; that's the compute. Model usage is the variable cost, and it is bounded: every session has a budget of tokens, calls and time that the harness enforces, and the hub shows usage back per person and per cost centre. The bigger cost is people: an enablement lead, two to four hours a week per champion, and review time from AI security engineers, of whom we need at least two so nothing waits on one person. There's no licence and no external service."),
              H1("What is not done, and who owns it"),
              P("Everything that can be finished without the bank's accounts is finished. What remains is a list of things only the bank can supply, each with an owner in the readiness page: group ids and app registrations from identity; secrets, a signing key, an inference profile and a bucket from the platform and integrations teams; the model approved by model risk; the base image pinned to our approved one; our own listings loaded into the hub; and the sign-offs themselves, which we have deliberately not filled in, because a sign-off is a person's word and we won't fake one."),
              H1("What we need from you"),
              steps(["Name the enablement lead and two AI security engineers.",
                     "Approve a first, read-only production step: the hub in staging, and the agent reading real tickets and deploy histories but writing nothing. The first write is a separate decision, gated by a demonstration.",
                     "Ask model risk to review the inference profile and the first-read evaluation.",
                     "Confirm the champions programme's cadence and the first cohort."]),
              H1("The next ninety days"),
              P("Weeks one to three: the open items closed and the staging deployment up; the first components used for real and signed. Weeks four to eight: the first cohort's briefs filed and two initiatives built on paved roads; the agent reading real incidents in staging. Weeks nine to thirteen: production for the hub and the read-only agent; the first write step proposed with its demonstration; the readiness page updated with measured numbers rather than estimates."),
              P("We'd rather you saw it than read about it. The walkthrough video is just under nine minutes, and a live demonstration with a poisoned ticket takes ten.", "callout")]


if __name__ == "__main__":
    for f, t, fn in [("user-manual.pdf", "The AI Hub and the Collection: user manual", manual), ("technical-guide.pdf", "The Collection: technical guide", technical), ("leadership-brief.pdf", "The AI Hub and the Collection: leadership brief", brief)]:
        print("wrote", build(f, t, fn))
