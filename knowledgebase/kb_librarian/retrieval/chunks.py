"""Split a page into heading-bounded chunks with stable ids and content hashes.

A chunk is one ``#``/``##``/``###`` section (heading line included; a heading-looking line inside a
fenced code block is code, as for links); the text before the first heading is the ``intro``. A
section longer than ``max_chars`` is cut at paragraph boundaries into ``slug``, ``slug-2``,
``slug-3`` … (a single over-long paragraph is cut hard). Ids are unique within a page whatever the
headings are, and the same body always yields the same chunks.
"""

import hashlib
import re
from dataclasses import dataclass

from kb_librarian.catalog.catalog import Document

MAX_CHUNK_CHARS = 3000
_HEADING = re.compile(r"^#{1,3} +(.*\S)\s*$")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_TOKEN = re.compile(r"\w+")


@dataclass(frozen=True)
class Chunk:
    id: str  # ``path#slug``
    path: str
    heading: str
    text: str
    hash: str  # sha256 over heading and text: the staleness key


def slugify(heading: str) -> str:
    return "-".join(_TOKEN.findall(heading.lower())) or "section"


def _sections(body: str) -> list[tuple[str, str]]:
    """``(heading, text)`` per section in page order; the first entry is the intro (heading ``""``)."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    fence: str | None = None
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        match = _HEADING.match(line) if fence is None else None
        if match:
            sections.append((match.group(1), [line]))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def _split(text: str, max_chars: int) -> list[str]:
    """Paragraph-bounded pieces of at most ``max_chars`` characters, in order."""
    pieces: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _PARAGRAPH_BREAK.split(text)):
        if not paragraph:
            continue
        while len(paragraph) > max_chars:  # one paragraph longer than a chunk: cut it hard
            if current:
                pieces.append(current)
                current = ""
            pieces.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        joined = f"{current}\n\n{paragraph}" if current else paragraph
        if len(joined) > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current = joined
    if current:
        pieces.append(current)
    return pieces


def _next_id(path: str, base: str, ordinal: int, used: set[str]) -> tuple[str, int]:
    """``path#base`` for a section's first piece, ``path#base-N`` after; N also moves past an id an
    earlier section with the same heading already took."""
    while True:
        chunk_id = f"{path}#{base}" if ordinal == 1 else f"{path}#{base}-{ordinal}"
        if chunk_id not in used:
            return chunk_id, ordinal
        ordinal += 1


def chunk_document(doc: Document, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    used: set[str] = set()
    for heading, text in _sections(doc.body):
        if not text:
            continue
        base, label = (slugify(heading), heading) if heading else ("intro", doc.title)
        ordinal = 0
        for piece in _split(text, max_chars):
            chunk_id, ordinal = _next_id(doc.rel_path, base, ordinal + 1, used)
            used.add(chunk_id)
            digest = hashlib.sha256(f"{label}\n{piece}".encode()).hexdigest()  # a title-only edit is a change too
            chunks.append(Chunk(id=chunk_id, path=doc.rel_path, heading=label, text=piece, hash=digest))
    return chunks
