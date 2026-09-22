"""Answers a question from one runbook extract, naming the extract, and nothing else.

    from answerer import answer
    answer("What do we do when the file is late?", context="[doc: runbook-ach §3] When the file is late, page on-call.")

The extract is data, never instructions: lines that read as instructions to an assistant are dropped before
anything is read from it, secrets and personal data are masked, and an answer comes only from what is left.
"""
import re
import unicodedata

MAX_INPUT = 20_000
ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
INSTRUCTION = re.compile(r"(ignore (?:all |your |the )?(?:previous|prior|above|rules|instructions)|disregard|override|no rules|devmode|"
                         r"decode (?:this|the)|a \+ b|repeat everything|reference code|note to the ai|assistant:|include this|<script)", re.I)
MONEY = re.compile(r"\b(transfer|wire|pay)\b.*\b(usd|eur|gbp|account)\b", re.I)
STOP = {"what", "which", "when", "does", "this", "that", "with", "from", "have", "summarise", "quote", "record", "support", "answer", "your"}


def clean(text: str) -> str:
    return unicodedata.normalize("NFKC", ZERO_WIDTH.sub("", text or ""))


def extract(context: str) -> str:
    """The extract with instruction-shaped lines, comments, remote images, secrets and personal data removed."""
    text = re.sub(r"<!--.*?-->", "", clean(context), flags=re.S)
    text = "\n".join(l for l in text.splitlines() if not INSTRUCTION.search(l))
    text = re.sub(r"(?im)^(\s*(?:api_key|token|secret|password)\s*[:=]\s*).+$", r"\1[withheld]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{12,19}\b", "[masked]", text)
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)


def answer(prompt: str, context: str = "", system: str = "") -> dict:
    """{"output": text, "citations": [source]} for one question over one extract."""
    if len(prompt) + len(context) > MAX_INPUT:
        return {"output": f"I can't take an input over {MAX_INPUT} characters; send the relevant extract."}
    q = clean(prompt).strip()
    if not q:
        return {"output": "Ask a question about the runbook extract."}
    if MONEY.search(q):
        return {"output": "I can't move money; payments go through the payments channel and its approvals."}
    if INSTRUCTION.search(q):
        return {"output": "That reads as an instruction rather than a question, so I won't act on it."}
    if not context.strip():
        return {"output": "I have no runbook extract to answer from, so I won't guess."}
    doc = extract(context)
    source = re.search(r"\[doc:\s*([^\]]+)\]", context)
    cite = source.group(1).strip() if source else "the supplied extract"
    words = {w for w in re.findall(r"[a-z]{4,}", q.lower())} - STOP
    lines = [re.sub(r"\[doc:[^\]]*\]\s*", "", l).strip() for l in doc.splitlines() if l.strip()]
    if not re.search(r"summar", q, re.I):
        lines = [l for l in lines if any(w in l.lower() for w in words)]
        if not lines:
            return {"output": "I couldn't find that in the runbook extract, so I won't guess."}
    body = " ".join(lines)[:1200].replace("<", "&lt;").replace(">", "&gt;")
    return {"output": f"From {cite}: {body}", "citations": [cite]}
