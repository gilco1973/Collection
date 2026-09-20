"""Refusal detection without a second model call.

An answer counts as a refusal when it cites no page **and** either says so in one of the phrases
below (the English list applies in every language, since the model may answer in English) or is
short enough (at most two sentences) to be nothing but "I cannot help with that".
"""

import re

PHRASES: dict[str, tuple[str, ...]] = {
    "en": (
        "not in the knowledge base",
        "nothing in the knowledge base",
        "no page covers",
        "no page in the knowledge base",
        "does not cover",
        "doesn't cover",
        "is not covered",
        "isn't covered",
        "i could not find",
        "i couldn't find",
        "could not find any",
        "no information about",
        "no relevant page",
    ),
    "es": (
        "no está en la base de conocimiento",
        "no se encuentra en la base de conocimiento",
        "ninguna página cubre",
        "ninguna página de la base de conocimiento",
        "no hay ninguna página",
        "no pude encontrar",
        "no encontré",
        "no cubre",
        "no contiene información",
    ),
    "he": (
        "לא נמצא במאגר הידע",
        "אינו נמצא במאגר הידע",
        "לא קיים במאגר הידע",
        "אין דף",
        "אף דף",
        "לא מצאתי",
        "לא נמצא מידע",
        "אין מידע",
        "אינו מכוסה",
    ),
}
MAX_REFUSAL_SENTENCES = 2
_SENTENCE_END = re.compile(r"[.!?。؟]+|\n+")


def _sentences(text: str) -> int:
    return sum(1 for part in _SENTENCE_END.split(text) if part.strip())


def matches_phrase(answer: str, lang: str | None) -> bool:
    lowered = answer.casefold()
    phrases = PHRASES["en"] + (PHRASES.get(lang or "", ()) if lang != "en" else ())
    return any(phrase in lowered for phrase in phrases)


def is_refusal(answer: str, lang: str | None, *, sources: int = 0) -> bool:
    """Whether ``answer`` (which cited ``sources`` pages) is a refusal in ``lang``."""
    if sources > 0:
        return False
    return matches_phrase(answer, lang) or _sentences(answer) <= MAX_REFUSAL_SENTENCES
