"""Minimal markdown → Confluence storage-format conversion.

Deliberately small: headings, paragraphs, bullet lists and fenced code. Anything
richer stays as escaped text so nothing is silently dropped or misrendered.
"""

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_SAFE_HREF = re.compile(r"^(https?:|mailto:|[^:]*$)", re.I)  # http(s), mail, or relative; never javascript:/data:


def _link(match: re.Match) -> str:
    label, href = match.group(1), match.group(2)
    return f'<a href="{href}">{label}</a>' if _SAFE_HREF.match(href) else f"{label} ({href})"


def _inline(text: str) -> str:
    escaped = html.escape(text)  # quotes too: a link target must not be able to close its href attribute
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    return _LINK.sub(_link, escaped)


def markdown_to_storage(markdown: str) -> str:
    out: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in markdown.splitlines():
        if line.startswith("```"):
            if in_code:
                out.append(
                    '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA['
                    + "\n".join(code)
                    + "]]></ac:plain-text-body></ac:structured-macro>"
                )
                code.clear()
            else:
                flush_paragraph()
                close_list()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        if heading:
            flush_paragraph()
            close_list()
            out.append(f"<h{len(heading.group(1))}>{_inline(heading.group(2))}</h{len(heading.group(1))}>")
        elif bullet:
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
        elif not line.strip():
            flush_paragraph()
            close_list()
        else:
            close_list()
            paragraph.append(line.strip())
    flush_paragraph()
    close_list()
    return "\n".join(out)
