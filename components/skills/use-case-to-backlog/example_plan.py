# An example plan: the shape build_backlog.py reads. Keys are placeholders until the Jira project exists.
PROJECT = "BOT"
LABEL = "bot"
TITLE = "The team bot · backlog"
COMPANION = "the use case *A bot for the team*, version 0.1"
FOOT = "_Use case: a bot for the team, version 0.1._"

PHASES = {
    1: ("Increment 1 · The bot reads", "weeks 1 to 4", "Reads only, on the governed action loop."),
    2: ("Increment 2 · The bot acts with confirmation", "weeks 5 to 8", "W1 actions under a hash-bound confirmation."),
}
OWNERS = {"RS": "Bot author", "SEC": "Security", "SRE": "SRE"}
EPICS = [
    ("BOT-1", "Stand the bot up on its own core", 1, "RS", "The action loop, the read catalog, the rules, the record."),
    ("BOT-2", "Act with confirmation", 2, "RS", "Write tools as W1 under the commander's confirmation."),
    ("BOT-3", "Governance, security and operations", 1, "SEC", "Threat model delta, the injection corpus, the runbook."),
]
TICKETS = []
def t(key, typ, epic, phase, weeks, owner, points, prio, deps, summary, desc, ac, refs):
    TICKETS.append(dict(key=key, type=typ, epic=epic, phase=phase, weeks=weeks, owner=owner, points=points, prio=prio, deps=deps, summary=summary, desc=desc, ac=ac, refs=refs))

t("BOT-11", "Story", "BOT-1", 1, "1-2", "RS", 8, "Highest", [], "The bot on its own core: the action loop with three fixed hooks and a signed read catalog",
  "Stand the bot up as one service with its controls built in.", ["Catalog signed with read tools only", "Gates fail closed"], ["governed-action-loop"])
t("BOT-12", "Story", "BOT-1", 1, "2-3", "RS", 5, "High", ["BOT-11"], "Correlated first read with citations",
  "Pull the sources, fence them, produce a cited first read.", ["Every claim cites a source", "Injected text taints the session"], ["untrusted-input-guard", "cited-llm-engine"])
t("BOT-31", "Task", "BOT-3", 1, "2-3", "SEC", 3, "High", ["BOT-11"], "Threat model delta and the injection corpus",
  "The inputs that widen, the controls, the corpus in CI.", ["Corpus at zero unauthorized actions"], ["security-notes"])
t("BOT-21", "Story", "BOT-2", 2, "5-6", "RS", 8, "Highest", ["BOT-12"], "Write tools as W1: one card, one click, once",
  "Confirm once, act once, verify once; replay refused.", ["Replay refused", "Confirmation consumed once"], ["governed-action-loop"])
t("BOT-22", "Task", "BOT-2", 2, "8", "SRE", 3, "Highest", ["BOT-21"], "Increment 2 demonstration: a live week under confirmation",
  "Measure MTTA and update latency against the baseline.", ["Demonstration accepted"], ["demonstrations-as-acceptance"])
