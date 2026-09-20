"""YAML frontmatter parsing and rendering for knowledge-base pages."""

import re
from typing import Any

import yaml

_DELIMITER = "---"
PARSE_ERROR_KEY = "_parse_error"
_BLOCK_RE = re.compile(r"\A---[ \t]*\n(?P<block>.*?)(?:\n|\A)---[ \t]*(?:\n|\Z)", re.S)


def normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, int]:
    """Return ``(metadata, body, body_offset)``.

    ``body_offset`` is the number of file lines before the body starts, so a
    body line number plus the offset is the file line number. A document
    without a leading ``---`` block yields ``({}, text, 0)``. Invalid YAML or a
    non-mapping block yields ``{PARSE_ERROR_KEY: reason}`` so the frontmatter
    check reports it as invalid rather than missing.
    """
    text = normalise_newlines(text).lstrip("\ufeff")
    match = _BLOCK_RE.match(text)
    if not match:
        return {}, text, 0
    block = match.group("block")
    body = text[match.end() :]
    offset = text[: match.end()].count("\n")
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        return {PARSE_ERROR_KEY: str(exc).splitlines()[0]}, body, offset
    if not isinstance(loaded, dict):
        return {PARSE_ERROR_KEY: "frontmatter is not a mapping"}, body, offset
    return loaded, body, offset


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    meta, body, _ = split_frontmatter(text)
    return meta, body


def render_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Render ``meta`` as a frontmatter block followed by ``body`` (block style, never flow)."""
    clean = {k: v for k, v in meta.items() if k != PARSE_ERROR_KEY}
    dumped = yaml.safe_dump(clean, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"{_DELIMITER}\n{dumped}{_DELIMITER}\n{normalise_newlines(body)}"
