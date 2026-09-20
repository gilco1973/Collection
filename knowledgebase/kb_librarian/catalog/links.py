"""Markdown link extraction: inline, reference-definition and autolinks outside code, with line numbers."""

import re
from dataclasses import dataclass

_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+\"[^\"]*\")?\)")
_REF_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_LIST_ITEM_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+")


@dataclass(frozen=True)
class Link:
    text: str
    target: str
    line: int  # file-relative

    @property
    def is_external(self) -> bool:
        return self.target.startswith(("http://", "https://", "mailto:"))


def extract_links(body: str, offset: int = 0) -> list[Link]:
    """Markdown links outside fenced blocks and inline code, with file-relative line numbers."""
    links: list[Link] = []
    fence: str | None = None
    in_code = in_list = False
    prev_blank = True
    for number, line in enumerate(body.splitlines(), start=1 + offset):
        stripped_start = line.lstrip()
        if stripped_start.startswith(("```", "~~~")):
            marker = stripped_start[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        if not line.strip():
            prev_blank = True
            continue
        indented = line.startswith(("    ", "\t"))
        # An indented block is code only when it opens after a blank line outside a list;
        # inside a list an indented line is a continuation paragraph or a nested item.
        in_code = indented and (in_code or (prev_blank and not in_list))
        prev_blank = False
        if in_code:
            continue
        if _LIST_ITEM_RE.match(line):
            in_list = True
        elif not indented:
            in_list = False
        stripped = _INLINE_CODE_RE.sub("", line)
        for match in _LINK_RE.finditer(stripped):
            links.append(Link(text=match.group(1), target=match.group(2).strip(), line=number))
        definition = _REF_DEF_RE.match(stripped)
        if definition:
            links.append(Link(text=definition.group(1), target=definition.group(2), line=number))
        for match in _AUTOLINK_RE.finditer(stripped):
            links.append(Link(text=match.group(1), target=match.group(1), line=number))
    return links
