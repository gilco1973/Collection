"""How to use a bot, explained inside the room: a how-to card with clickable prompt pills, a one-line first-time hint,
and a five-step guide page. Borrowed from incident tooling (the pinned "here is what to do first" message) and from
product advisors (starter prompts grouped by category and filtered by what the person may do), so nobody has to
remember syntax under stress.

Configure `Bot` with your pills, steps, roles and the "never does" sentence; everything else renders from it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import html

CARD_VERSION = "1.5"


@dataclass(frozen=True)
class Pill:
    id: str
    label: str          # the chip text
    command: str        # what is sent as if typed; a `<placeholder>` makes it a hint rather than a button
    category: str       # Read | Act | Mitigate | Wrap up (any order you like; the card keeps yours)
    tier: str           # R | W1 | W2
    needs: tuple = ()   # roles a person needs to see it; () = anyone admitted


@dataclass
class Bot:
    name: str                                   # how people address it: "@Meg"
    what_it_is: str                             # one sentence
    three_things: tuple                         # the three things to know
    pills: list
    steps: list                                 # [(title, html)]
    roles: list                                 # [(role, what they do)]
    never: str                                  # what it never does, one sentence
    categories: tuple = ("Read", "Act", "Mitigate", "Wrap up")
    tiers_by_increment: dict = field(default_factory=lambda: {1: {"R"}, 2: {"R", "W1"}, 3: {"R", "W1", "W2"}})

    def visible_pills(self, roles: list, increment: int) -> list:
        tiers = self.tiers_by_increment[increment]
        return [p for p in self.pills if p.tier in tiers and all(r in roles for r in p.needs)]

    def who_says_yes(self, tier: str) -> str:
        return {"R": "no confirmation", "W1": "you confirm once", "W2": "a second person approves"}[tier]

    def welcome_card(self, context: dict, base_url: str, roles: list | None = None, increment: int = 3) -> dict:
        """An Adaptive Card: three things to know, starter pills by category (up to six as buttons), the roles, the guide link."""
        t = lambda text, **kw: {"type": "TextBlock", "text": text, "wrap": True, **kw}
        body = [t(f"How to work with {self.name} here", size="Medium", weight="Bolder"), t(self.what_it_is.format(**context)), t("**Three things to know**", spacing="Medium"),
                t("\n".join(f"{i}. {x}" for i, x in enumerate(self.three_things, 1))), t("**Try one of these**", spacing="Medium")]
        actions = []
        pills = self.visible_pills(roles or [], increment)
        for cat in self.categories:
            ps = [p for p in pills if p.category == cat]
            if not ps: continue
            body.append(t(f"_{cat}_: " + " · ".join(f"`{self.name} {p.command}`" for p in ps), size="Small", isSubtle=True))
            for p in ps[:3]:
                if "<" not in p.command:
                    actions.append({"type": "Action.Submit", "title": p.label, "data": {"bot": "command", "text": p.command, **context}})
        body.append(t("**Who does what**: " + " · ".join(f"{r}: {d}" for r, d in self.roles), size="Small", spacing="Medium"))
        body.append(t(self.never, size="Small", isSubtle=True))
        actions = actions[:6] + [{"type": "Action.OpenUrl", "title": "The five-step guide", "url": f"{base_url}/help"}]
        return {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": CARD_VERSION, "body": body, "actions": actions}

    def first_time_hint(self, person: str) -> str:
        return (f"Hi {person}. Quick orientation: any plain message is a question; `{self.name} status` shows where we are; `{self.name} help` shows every command. "
                "Every action is a card you confirm once, and everything lands on the record.")

    def guide_html(self, context: dict | None = None) -> str:
        intro = self.what_it_is.format_map(_Defaults(context or {}))
        steps = "".join(f"<li><b>{html.escape(t)}.</b> {d}</li>" for t, d in self.steps)
        roles = "".join(f"<tr><td><b>{html.escape(r)}</b></td><td>{html.escape(d)}</td></tr>" for r, d in self.roles)
        cats = ""
        for cat in self.categories:
            rows = "".join(f"<tr><td><code>{html.escape(self.name)} {html.escape(p.command)}</code></td><td>{html.escape(p.label)}</td><td>{self.who_says_yes(p.tier)}</td></tr>" for p in self.pills if p.category == cat)
            if rows: cats += f"<h3>{cat}</h3><table><tr><th>Command</th><th>What it does</th><th>Who says yes</th></tr>{rows}</table>"
        return (f"<h1>Using {html.escape(self.name)}: your first time in five steps</h1><p>{html.escape(intro)}</p>"
                f"<ol>{steps}</ol><h2>Who does what</h2><table>{roles}</table><h2>Every command</h2>{cats}<h2>What it never does</h2><p>{html.escape(self.never)}</p>")


class _Defaults(dict):
    """A format map that leaves unknown placeholders readable ("{service}" becomes "the service")."""
    def __missing__(self, key):
        return "the " + key.replace("_", " ")


EXAMPLE = Bot(
    name="@Bot", what_it_is="The bot is the first responder for {service} here. It has assembled the room and posted the first read. You stay in charge.",
    three_things=("**Ask anything in plain words.** A message that is not a command is a question; answers carry source tags.",
                  "**Actions need your confirmation.** One card, one click, once.",
                  "**Mitigations need two people.** You request, an owner approves, you execute, the bot verifies."),
    pills=[Pill("status", "What is the state right now?", "status", "Read", "R"), Pill("changed", "What changed before the alert?", "ask what changed in the last hour", "Read", "R"),
           Pill("ack", "Acknowledge the page as me", "ack", "Act", "W1"), Pill("action", "Record an action item", "action <what, and who>", "Act", "R"),
           Pill("mitigate", "Propose a mitigation for the owner", "mitigate", "Mitigate", "W2"), Pill("close", "Close and draft the postmortem", "close", "Wrap up", "R")],
    steps=[("Read the first read", "What changed, what is failing, the hypothesis with its evidence."), ("Take the page", "Type <b>@Bot ack</b>; confirm once."),
           ("Keep people informed", "<b>@Bot update internal</b> fills the template; you confirm."), ("Fix it under dual control", "<b>@Bot mitigate</b>; an owner approves; you execute."),
           ("Close and learn", "<b>@Bot close</b> drafts the postmortem from the record.")],
    roles=[("Commander", "confirms actions"), ("Service owner", "approves mitigations; never their own"), ("Everyone", "asks questions, adds action items")],
    never="The bot never changes production on its own, never sends free text to a customer, and never acts from a session that carried a hidden instruction.")
