# A five-slide example plan for deck.py. Shots are PNG files under shots/ captured from the real product.
TITLE = "The team bot: walkthrough"
FOOT = "The team bot · walkthrough v1 · internal"
SLIDES = [
    ("title", "The team", "The team bot, in four minutes", ["One incident from the page to the postmortem", "What the bot does, what it asks of you, what it never does"], None,
     "This is the team bot. In the next four minutes we follow one incident from the page to the postmortem and see what the bot does, what it asks of you, and what it never does."),
    ("page", "Step 1 · The page", "The page fires. The bot opens the room", ["A channel per incident", "The incident card, pinned", "The on-call mentioned and made commander"], "01-room.png",
     "Step one. The page fires. Within seconds the bot opens a room, posts the incident card, pins it, and mentions the on-call engineer."),
    ("read", "Step 2 · The first read", "Within two minutes: what changed, what is failing", ["Every claim carries a source tag you can open", "A confidence line, not a guess"], "02-firstread.png",
     "Step two. Within two minutes the bot posts the first read: what changed, what is failing, and the leading hypothesis with its sources."),
    ("act", "Step 3 · Act", "One card, one click, once", ["The bot prepares the action as a card", "Only the commander confirms; a second click is refused", "The bot acts, verifies, records"], "03-ack.png",
     "Step three. The bot prepares every action as a card. You confirm once. The bot acts, verifies, and writes it to the timeline."),
    ("never", "What it never does", "You stay in charge", ["No production change on the model's say-so", "No free text to customers", "Stop it from the console at any time"], None,
     "What the bot never does: it never changes production on its own and never sends free text to a customer. You can stop it from the console at any time. Thank you."),
]
