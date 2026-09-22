#!/usr/bin/env python3
"""Split the teaching guide into Confluence pages, one per chapter.

    python3 docs/teaching/build_confluence.py            # writes docs/teaching/confluence/
    python3 docs/teaching/build_confluence.py --check    # refuses when the written tree is stale
    python3 docs/teaching/build_confluence.py --out DIR  # write somewhere else
    python3 docs/teaching/build_confluence.py --zip F.zip # the pages, attachments, uploader and README as one zip

The source is docs/teaching/teaching-the-collection.html. Every <section> becomes one page in Confluence storage
format (the XHTML the REST API and the page editor take), under an index page that lists its children. Screenshots
leave the page as JPEG attachments; the four process diagrams are drawn to PNG and their Mermaid source travels
with them in a collapsed block. A Markdown copy of every page is written for pasting by hand, and pages.json is
the manifest upload.py reads. Standard library plus Pillow for the diagrams.

Rules of the conversion (what Confluence keeps): headings, paragraphs, tables, lists, bold, italics, code, links,
images by attachment name, and the status, code, panel, expand, anchor and children macros. Classes and inline
styles do not survive, so every construct of the page is mapped to one of those.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "teaching-the-collection.html")
OUT = os.path.join(HERE, "confluence")
INDEX_TITLE = "Teaching the Collection"
STATUS_COLOUR = {"ok": "Green", "warn": "Yellow", "crit": "Red", "money": "Purple", "accent": "Blue"}
PANEL = {"warn": "warning", "ok": "tip"}
VOID = {"img", "br", "meta", "link", "input", "hr"}


# --- a small DOM -------------------------------------------------------------------------------------------------

class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict):
        self.tag, self.attrs, self.children = tag, attrs, []

    def classes(self) -> set:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find_all(self, tag: str) -> list:
        out = []
        for c in self.children:
            if isinstance(c, Node):
                if c.tag == tag:
                    out.append(c)
                out.extend(c.find_all(tag))
        return out

    def first(self, tag: str):
        found = self.find_all(tag)
        return found[0] if found else None

    def elements(self) -> list:
        return [c for c in self.children if isinstance(c, Node)]


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs))
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> Node:
    t = Tree()
    t.feed(html)
    t.close()
    return t.root


# --- text helpers ------------------------------------------------------------------------------------------------

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def attr(s: str) -> str:
    return esc(s).replace('"', "&quot;")


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60].rstrip("-")


def heading_parts(h2: Node) -> tuple:
    """The chapter title and its one-line subtitle (the <small>)."""
    title = "".join(c for c in h2.children if isinstance(c, str)).strip()
    small = h2.first("small")
    return squash(title), squash(small.text()).strip() if small else ""


# --- Confluence storage format -----------------------------------------------------------------------------------

def macro(name: str, params: dict | None = None, rich: str = "", plain: str | None = None) -> str:
    out = [f'<ac:structured-macro ac:name="{name}" ac:schema-version="1">']
    for k, v in (params or {}).items():
        out.append(f'<ac:parameter ac:name="{k}">{esc(v)}</ac:parameter>')
    if plain is not None:
        if "]]>" in plain:
            raise ValueError("a code block contains ']]>'")
        out.append(f"<ac:plain-text-body><![CDATA[{plain}]]></ac:plain-text-body>")
    if rich:
        out.append(f"<ac:rich-text-body>{rich}</ac:rich-text-body>")
    out.append("</ac:structured-macro>")
    return "".join(out)


def status(text: str, cls: set) -> str:
    colour = next((STATUS_COLOUR[c] for c in STATUS_COLOUR if c in cls), "Grey")
    return macro("status", {"colour": colour, "title": squash(text).strip()})


def code_block(text: str, language: str | None = "bash") -> str:
    return macro("code", {"language": language} if language else {}, plain=text)


def image(filename: str, width: int = 900) -> str:
    return f'<p><ac:image ac:width="{width}"><ri:attachment ri:filename="{attr(filename)}" /></ac:image></p>'


class Storage:
    """Emits storage-format XHTML for the constructs the teaching page uses."""

    def __init__(self, page):
        self.page = page   # receives attachments and diagrams

    # inline -------------------------------------------------------------------------------------------------------
    def inline(self, nodes, plain_chips: bool = False) -> str:
        out = []
        for c in nodes:
            if isinstance(c, str):
                out.append(esc(squash(c)))
                continue
            cls = c.classes()
            if c.tag == "span" and "t" in cls:
                out.append(f"<code>{self.inline(c.children, plain_chips)}</code>")
            elif c.tag == "span" and "chip" in cls:
                out.append(f"({esc(squash(c.text()).strip()) })" if plain_chips else status(c.text(), cls))
            elif c.tag in ("b", "strong"):
                out.append(f"<strong>{self.inline(c.children, plain_chips)}</strong>")
            elif c.tag in ("i", "em", "small"):
                out.append(f"<em>{self.inline(c.children, plain_chips)}</em>")
            elif c.tag == "code":
                out.append(f"<code>{self.inline(c.children, plain_chips)}</code>")
            elif c.tag == "br":
                out.append("<br />")
            elif c.tag == "a" and c.attrs.get("href", "").startswith("http"):
                out.append(f'<a href="{attr(c.attrs["href"])}">{self.inline(c.children, plain_chips)}</a>')
            else:
                out.append(self.inline(c.children, plain_chips))
        return "".join(out).strip()

    # blocks -------------------------------------------------------------------------------------------------------
    def blocks(self, nodes) -> str:
        out = []
        for n in nodes:
            if isinstance(n, str):
                if n.strip():
                    out.append(f"<p>{esc(squash(n).strip())}</p>")
                continue
            cls = n.classes()
            if n.tag == "h2":
                continue   # the chapter heading is the page title
            if n.tag == "h3":
                if n.attrs.get("id"):
                    out.append(macro("anchor", {"": n.attrs["id"]}))
                out.append(f"<h2>{self.inline(n.children, plain_chips=True)}</h2>")
            elif n.tag == "figure":
                out.append(self.figure(n))
            elif n.tag == "div" and "scroll" in cls:
                out.append(self.blocks(n.children))
            elif n.tag == "table":
                out.append(self.table(n))
            elif n.tag == "ol" and "steps" in cls:
                out.append(self.steps(n))
            elif n.tag in ("ol", "ul"):
                out.append(self.list(n))
            elif n.tag == "div" and "note" in cls:
                kind = next((PANEL[c] for c in PANEL if c in cls), "info")
                out.append(macro(kind, rich=f"<p>{self.inline(n.children)}</p>"))
            elif n.tag == "div" and "cards" in cls:
                out.append(self.cards(n))
            elif n.tag == "div" and "lesson" in cls:
                out.append(self.lesson(n))
            elif n.tag == "dl":
                out.append(self.definitions(n))
            elif n.tag == "pre" and "mermaid" in cls:
                out.append(self.diagram(n))
            elif n.tag == "code" and "cmd" in cls:
                out.append(code_block(n.text().strip()))
            elif n.tag == "p":
                out.append(f"<p>{self.inline(n.children)}</p>")
            else:
                out.append(f"<p>{self.inline(n.children)}</p>")
        return "".join(out)

    def figure(self, n: Node) -> str:
        img = n.first("img")
        cap = n.first("figcaption")
        filename = self.page.attach_image(img.attrs["src"], img.attrs.get("alt", ""))
        caption = f"<p><em>{self.inline(cap.children)}</em></p>" if cap else ""
        return image(filename) + caption

    def table(self, n: Node) -> str:
        rows = []
        for tr in n.find_all("tr"):
            cells = []
            for cell in tr.elements():
                if cell.tag in ("th", "td"):
                    cells.append(f"<{cell.tag}>{self.inline(cell.children) or '&nbsp;'}</{cell.tag}>")
            rows.append(f"<tr>{''.join(cells)}</tr>")
        return f"<table><tbody>{''.join(rows)}</tbody></table>"

    def steps(self, n: Node) -> str:
        items = []
        for li in n.elements():
            body = li.first("div") or li
            head = [c for c in body.children if isinstance(c, Node) and c.tag == "b"]
            why = [c for c in body.children if isinstance(c, Node) and c.tag == "span" and "why" in c.classes()]
            rest = [c for c in body.children if c not in head and c not in why]
            text = f"<strong>{self.inline(head[0].children)}</strong>" if head else self.inline(rest)
            if head and rest and self.inline(rest):
                text += " " + self.inline(rest)
            if why:
                text += f"<br />{self.inline(why[0].children)}"
            items.append(f"<li><p>{text}</p></li>")
        return f"<ol>{''.join(items)}</ol>"

    def list(self, n: Node) -> str:
        items = []
        for li in n.elements():
            if li.tag != "li":
                continue
            cmd = [c for c in li.children if isinstance(c, Node) and c.tag == "code" and "cmd" in c.classes()]
            if cmd:
                text = self.inline([c for c in li.children if c not in cmd])
                items.append(f"<li>{('<p>' + text + '</p>') if text else ''}{code_block(cmd[0].text().strip())}</li>")
            else:
                items.append(f"<li>{self.inline(li.children)}</li>")
        return f"<{n.tag}>{''.join(items)}</{n.tag}>"

    def cards(self, n: Node) -> str:
        out = []
        for card in n.elements():
            head = next((c for c in card.children if isinstance(c, Node) and c.tag == "b"), None)
            rest = [c for c in card.children if c is not head]
            if head:
                out.append(f"<h3>{self.inline(head.children, plain_chips=True)}</h3>")
            inline_run, blocks = [], []
            for c in rest:
                if isinstance(c, Node) and c.tag in ("ol", "ul"):
                    if self.inline(inline_run):
                        blocks.append(f"<p>{self.inline(inline_run)}</p>")
                    inline_run = []
                    blocks.append(self.list(c))
                else:
                    inline_run.append(c)
            if self.inline(inline_run):
                blocks.append(f"<p>{self.inline(inline_run)}</p>")
            out.extend(blocks)
        return "".join(out)

    def lesson(self, n: Node) -> str:
        spans = n.elements()
        rows = ["<tr><th>Minutes</th><th>What happens</th></tr>"]
        for i in range(0, len(spans) - 1, 2):
            rows.append(f"<tr><td>{self.inline(spans[i].children)}</td><td>{self.inline(spans[i + 1].children)}</td></tr>")
        return f"<table><tbody>{''.join(rows)}</tbody></table>"

    def definitions(self, n: Node) -> str:
        rows = ["<tr><th>Term</th><th>What it means</th></tr>"]
        term = None
        for c in n.elements():
            if c.tag == "dt":
                term = self.inline(c.children)
            elif c.tag == "dd":
                rows.append(f"<tr><td><strong>{term}</strong></td><td>{self.inline(c.children)}</td></tr>")
        return f"<table><tbody>{''.join(rows)}</tbody></table>"

    def diagram(self, n: Node) -> str:
        source = mermaid_source(n)
        filename = self.page.attach_diagram(source)
        return image(filename) + macro("expand", {"title": "Diagram source (Mermaid)"}, rich=code_block(source, None))


def mermaid_source(pre: Node) -> str:
    parts = []
    for c in pre.children:
        parts.append(c if isinstance(c, str) else ("<br/>" if c.tag == "br" else c.text()))
    lines = "".join(parts).strip("\n").splitlines()
    indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(l[indent:].rstrip() for l in lines).strip()


# --- Markdown ----------------------------------------------------------------------------------------------------

class Markdown:
    def __init__(self, page):
        self.page = page

    def inline(self, nodes) -> str:
        out = []
        for c in nodes:
            if isinstance(c, str):
                out.append(squash(c))
                continue
            cls = c.classes()
            if c.tag == "span" and ("t" in cls or "chip" in cls) or c.tag == "code":
                out.append(f"`{squash(c.text()).strip()}`")
            elif c.tag in ("b", "strong"):
                out.append(f"**{self.inline(c.children).strip()}**")
            elif c.tag in ("i", "em", "small"):
                out.append(f"*{self.inline(c.children).strip()}*")
            elif c.tag == "br":
                out.append(" ")
            else:
                out.append(self.inline(c.children))
        return "".join(out).strip()

    def cell(self, nodes) -> str:
        return self.inline(nodes).replace("|", "\\|") or " "

    def blocks(self, nodes) -> str:
        out = []
        for n in nodes:
            if isinstance(n, str):
                if n.strip():
                    out.append(squash(n).strip())
                continue
            cls = n.classes()
            if n.tag == "h2":
                continue   # the chapter heading is the page title
            if n.tag == "h3":
                out.append(f"## {self.inline(n.children)}")
            elif n.tag == "figure":
                img, cap = n.first("img"), n.first("figcaption")
                filename = self.page.attach_image(img.attrs["src"], img.attrs.get("alt", ""))
                out.append(f"![{squash(img.attrs.get('alt', ''))}](../attachments/{self.page.slug}/{filename})")
                if cap:
                    out.append(f"*{self.inline(cap.children)}*")
            elif n.tag == "div" and "scroll" in cls:
                out.append(self.blocks(n.children))
            elif n.tag == "table":
                out.append(self.table(n))
            elif n.tag == "ol" and "steps" in cls:
                out.append(self.steps(n))
            elif n.tag in ("ol", "ul"):
                out.append(self.list(n))
            elif n.tag == "div" and "note" in cls:
                mark = "Warning" if "warn" in cls else "Takeaway" if "ok" in cls else "Note"
                out.append(f"> **{mark}.** {self.inline(n.children)}")
            elif n.tag == "div" and "cards" in cls:
                out.append(self.cards(n))
            elif n.tag == "div" and "lesson" in cls:
                spans = n.elements()
                rows = ["| Minutes | What happens |", "| --- | --- |"]
                for i in range(0, len(spans) - 1, 2):
                    rows.append(f"| {self.cell(spans[i].children)} | {self.cell(spans[i + 1].children)} |")
                out.append("\n".join(rows))
            elif n.tag == "dl":
                rows = ["| Term | What it means |", "| --- | --- |"]
                term = ""
                for c in n.elements():
                    if c.tag == "dt":
                        term = self.cell(c.children)
                    elif c.tag == "dd":
                        rows.append(f"| **{term}** | {self.cell(c.children)} |")
                out.append("\n".join(rows))
            elif n.tag == "pre" and "mermaid" in cls:
                source = mermaid_source(n)
                filename = self.page.attach_diagram(source)
                out.append(f"![diagram](../attachments/{self.page.slug}/{filename})")
                out.append(f"```mermaid\n{source}\n```")
            elif n.tag == "code" and "cmd" in cls:
                out.append(f"```bash\n{n.text().strip()}\n```")
            else:
                out.append(self.inline(n.children))
        return "\n\n".join(b for b in out if b)

    def table(self, n: Node) -> str:
        rows = []
        for tr in n.find_all("tr"):
            cells = [self.cell(c.children) for c in tr.elements() if c.tag in ("th", "td")]
            rows.append("| " + " | ".join(cells) + " |")
            if len(rows) == 1:
                rows.append("|" + " --- |" * len(cells))
        return "\n".join(rows)

    def steps(self, n: Node) -> str:
        items = []
        for i, li in enumerate(n.elements(), 1):
            body = li.first("div") or li
            head = [c for c in body.children if isinstance(c, Node) and c.tag == "b"]
            why = [c for c in body.children if isinstance(c, Node) and c.tag == "span" and "why" in c.classes()]
            text = f"**{self.inline(head[0].children)}**" if head else self.inline(body.children)
            if why:
                text += f"  \n   {self.inline(why[0].children)}"
            items.append(f"{i}. {text}")
        return "\n".join(items)

    def list(self, n: Node) -> str:
        items = []
        for i, li in enumerate([c for c in n.elements() if c.tag == "li"], 1):
            cmd = [c for c in li.children if isinstance(c, Node) and c.tag == "code" and "cmd" in c.classes()]
            mark = f"{i}." if n.tag == "ol" else "-"
            if cmd:
                text = self.inline([c for c in li.children if c not in cmd])
                items.append(f"{mark} {text}\n\n   ```bash\n" + "\n".join("   " + l for l in cmd[0].text().strip().splitlines()) + "\n   ```")
            else:
                items.append(f"{mark} {self.inline(li.children)}")
        return "\n".join(items)

    def cards(self, n: Node) -> str:
        out = []
        for card in n.elements():
            head = next((c for c in card.children if isinstance(c, Node) and c.tag == "b"), None)
            rest = [c for c in card.children if c is not head]
            if head:
                out.append(f"### {self.inline(head.children)}")
            run = []
            for c in rest:
                if isinstance(c, Node) and c.tag in ("ol", "ul"):
                    if self.inline(run):
                        out.append(self.inline(run))
                    run = []
                    out.append(self.list(c))
                else:
                    run.append(c)
            if self.inline(run):
                out.append(self.inline(run))
        return "\n\n".join(out)


# --- diagrams: a layered drawing of a Mermaid "flowchart LR" -----------------------------------------------------

EDGE = re.compile(r"\s*(?:-->|--\s*(?P<label>[^-]+?)\s*-->|-\.\s*(?P<dashed>[^.]+?)\s*\.->)\s*")
NODE = re.compile(r"(?P<id>[A-Za-z0-9_]+)(?:(?P<open>[\[{])(?P<label>.*?)(?P<close>[\]}]))?")


def parse_flowchart(source: str) -> tuple:
    """Nodes in order of first mention ({id: (label lines, shape)}) and edges (src, dst, label, dashed)."""
    nodes: dict = {}
    edges: list = []
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("flowchart") or line.startswith("%%"):
            continue
        pos = 0
        prev = None
        while pos < len(line):
            m = NODE.match(line, pos)
            if not m:
                raise ValueError(f"cannot read diagram line: {line!r}")
            nid = m.group("id")
            if m.group("label") is not None:
                nodes[nid] = (re.split(r"<br\s*/?>", m.group("label").strip()), "diamond" if m.group("open") == "{" else "box")
            elif nid not in nodes:
                nodes[nid] = ([nid], "box")
            if prev is not None:
                edges.append((prev[0], nid, prev[1], prev[2]))
            pos = m.end()
            e = EDGE.match(line, pos)
            if not e:
                break
            prev = (nid, e.group("label") or e.group("dashed") or "", e.group("dashed") is not None)
            pos = e.end()
    return nodes, edges


FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Unicode.ttf", "C:/Windows/Fonts/arial.ttf")


def load_font(size: int):
    from PIL import ImageFont
    for path in FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(size=size), False   # Pillow's bundled face has no arrow glyphs


def draw_flowchart(source: str) -> bytes:
    """A top-to-bottom drawing of the flowchart: one row per layer (longest path from the sources), boxes and
    diamonds as the source says, labels on the edges, a back edge routed down the right-hand side."""
    import math
    from PIL import Image, ImageDraw

    nodes, edges = parse_flowchart(source)
    order = list(nodes)
    forward = [e for e in edges if order.index(e[1]) > order.index(e[0])]
    back = [e for e in edges if e not in forward]
    layer = {n: 0 for n in nodes}
    for _ in range(len(nodes) + 1):
        for s, d, _l, _d in forward:
            layer[d] = max(layer[d], layer[s] + 1)
    font, arrows = load_font(26)
    small, _ = load_font(22)
    fix = (lambda t: t) if arrows else (lambda t: t.replace("\u2192", "->").replace("\u2190", "<-"))
    pad_x, pad_y, line_h, gap_x, gap_y, margin = 26, 18, 34, 60, 110, 40

    size = {}
    for n, (lines, shape) in nodes.items():
        lines = [fix(l) for l in lines]
        nodes[n] = (lines, shape)
        w, h = max(int(font.getlength(l)) for l in lines) + 2 * pad_x, len(lines) * line_h + 2 * pad_y
        if shape == "diamond":
            w, h = int(w * 1.6), int(h * 1.9)
        size[n] = (w, h)
    rows: dict = {}
    for n in order:
        rows.setdefault(layer[n], []).append(n)
    row_h = {r: max(size[n][1] for n in ns) for r, ns in rows.items()}
    row_w = {r: sum(size[n][0] for n in ns) + gap_x * (len(ns) - 1) for r, ns in rows.items()}
    gutter = max([int(small.getlength(fix(e[2]))) + 60 for e in back] + [0])   # room for a back edge and its label
    width = max(row_w.values()) + 2 * margin + gutter
    y = margin
    pos = {}
    for r in sorted(rows):
        x = (width - gutter - row_w[r]) // 2
        for n in rows[r]:
            w, h = size[n]
            pos[n] = (x, y + (row_h[r] - h) // 2, w, h)
            x += w + gap_x
        y += row_h[r] + gap_y
    height = y - gap_y + margin
    img = Image.new("RGB", (width, height), "#ffffff")
    d = ImageDraw.Draw(img)
    ink, accent, soft, rule = "#0f172a", "#2757a8", "#e6eef9", "#94a3b8"

    def curve(p0, p1, p2, p3, steps=40):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            a, b, c_, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
            pts.append((a * p0[0] + b * p1[0] + c_ * p2[0] + e * p3[0], a * p0[1] + b * p1[1] + c_ * p2[1] + e * p3[1]))
        return pts

    def arrow(tip, frm, colour):
        ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
        a1 = (tip[0] - 16 * math.cos(ang - 0.45), tip[1] - 16 * math.sin(ang - 0.45))
        a2 = (tip[0] - 16 * math.cos(ang + 0.45), tip[1] - 16 * math.sin(ang + 0.45))
        d.polygon([tip, a1, a2], fill=colour)

    def dashed_line(pts, colour):
        for i in range(0, len(pts) - 1, 2):
            d.line([pts[i], pts[i + 1]], fill=colour, width=3)

    def label_at(x0, y0, text, colour):
        if not text:
            return
        text = fix(text)
        tw, th = int(small.getlength(text)), 26
        d.rectangle([x0 - tw // 2 - 8, y0 - th // 2 - 4, x0 + tw // 2 + 8, y0 + th // 2 + 4], fill="#ffffff", outline=rule)
        d.text((x0 - tw // 2, y0 - th // 2 + 1), text, fill=colour, font=small)

    for s, t, label, dashed in forward:
        sx, sy, sw, sh = pos[s]
        tx, ty, tw_, th_ = pos[t]
        p0, p3 = (sx + sw // 2, sy + sh), (tx + tw_ // 2, ty)
        dy = max(40, (p3[1] - p0[1]) // 2)
        pts = curve(p0, (p0[0], p0[1] + dy), (p3[0], p3[1] - dy), p3)
        colour = "#475569" if dashed else ink
        dashed_line(pts, colour) if dashed else d.line(pts, fill=colour, width=3)
        arrow(p3, pts[-4], colour)
        mid = pts[int(len(pts) * 0.62)]   # past the fan-out, where labels of sibling edges no longer overlap
        label_at(int(mid[0]), int(mid[1]), label, ink)
    for s, t, label, dashed in back:
        sx, sy, sw, sh = pos[s]
        tx, ty, tw_, th_ = pos[t]
        xr = width - gutter // 2
        p0, p1, p2, p3 = (sx + sw, sy + sh // 2), (xr, sy + sh // 2), (xr, ty + th_ // 2), (tx + tw_, ty + th_ // 2)
        colour = "#475569"
        for a, b in zip([p0, p1, p2, p3], [p1, p2, p3]):
            n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) // 14))
            dashed_line([(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)], colour)
        arrow(p3, (p3[0] + 20, p3[1]), colour)
        label_at(xr, (p1[1] + p2[1]) // 2, label, colour)
    for n, (lines, shape) in nodes.items():
        px, py, w, h = pos[n]
        if shape == "diamond":
            d.polygon([(px + w // 2, py), (px + w, py + h // 2), (px + w // 2, py + h), (px, py + h // 2)], fill=soft, outline=accent, width=3)
        else:
            d.rounded_rectangle([px, py, px + w, py + h], radius=14, fill="#ffffff", outline=accent, width=3)
        ty = py + (h - len(lines) * line_h) // 2 + 2
        for l in lines:
            d.text((px + (w - int(font.getlength(l))) // 2, ty), l, fill=ink, font=font)
            ty += line_h
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# --- pages -------------------------------------------------------------------------------------------------------

class Page:
    def __init__(self, order: int, title: str, subtitle: str, section: Node | None):
        self.order, self.title, self.subtitle, self.section = order, title, subtitle, section
        m = re.match(r"(\d+)\.\s*(.*)", title)
        self.slug = f"{int(m.group(1)):02d}-{slugify(m.group(2))}" if m else f"00-{slugify(title)}"
        self.files: dict = {}          # attachment filename -> bytes
        self._n = 0

    def attach_image(self, src: str, alt: str) -> str:
        m = re.match(r"data:image/(\w+);base64,(.*)$", src, re.S)
        if not m:
            raise ValueError(f"{self.title}: an image is not inline data")
        ext = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}[m.group(1)]
        data = base64.b64decode(m.group(2))
        for name, existing in self.files.items():
            if existing == data:
                return name
        self._n += 1
        name = f"{self.slug}-{self._n:02d}.{ext}"
        self.files[name] = data
        return name

    def attach_diagram(self, source: str) -> str:
        digest = hashlib.sha256(source.encode()).hexdigest()[:8]
        for name in self.files:
            if name.endswith(f"-{digest}.png"):
                return name
        self._n += 1
        name = f"{self.slug}-{self._n:02d}-{digest}.png"
        self.files[name] = draw_flowchart(source)
        return name

    def storage(self) -> str:
        body = [f"<p><em>{esc(self.subtitle)}</em></p>"] if self.subtitle else []
        body.append(Storage(self).blocks(self.section.children if self.section else []))
        return "".join(body)

    def markdown(self) -> str:
        head = [f"# {self.title}"]
        if self.subtitle:
            head.append(f"*{self.subtitle}*")
        return "\n\n".join(head + [Markdown(self).blocks(self.section.children if self.section else [])]) + "\n"


def index_page(root: Node, pages: list) -> tuple:
    header = next(n for n in root.find_all("header") if "top" in n.classes())
    lede = header.first("p")
    howto = next(n for n in header.find_all("div") if "howto" in n.classes())
    s = Storage(None)
    rows = ["<tr><th>How this guide is written</th><th>&nbsp;</th></tr>"]
    for tile in howto.elements():
        b = tile.first("b")
        rest = [c for c in tile.children if c is not b]
        rows.append(f"<tr><td><strong>{s.inline(b.children)}</strong></td><td>{s.inline(rest)}</td></tr>")
    storage = (
        f"<p><em>{s.inline(lede.children)}</em></p>"
        f"<table><tbody>{''.join(rows)}</tbody></table>"
        "<h2>Chapters</h2>"
        + macro("children", {"all": "true", "sort": "creation"})
        + macro("info", rich="<p>These pages are generated from the teaching guide's one source file; a correction goes there and is uploaded again, "
                             "so nothing edited here by hand survives the next upload.</p>")
    )
    md = Markdown(None)
    lines = [f"# {INDEX_TITLE}", f"*{md.inline(lede.children)}*", "| How this guide is written | |", "| --- | --- |"]
    for tile in howto.elements():
        b = tile.first("b")
        rest = [c for c in tile.children if c is not b]
        lines.append(f"| **{md.cell(b.children)}** | {md.cell(rest)} |")
    lines.append("## Chapters")
    lines.append("\n".join(f"{i}. [{p.title}]({p.slug}.md)" for i, p in enumerate(pages, 1)))
    return storage, "\n\n".join(lines) + "\n"


def build(source: str = SOURCE) -> tuple:
    """Returns (manifest, files) where files maps a relative path to bytes."""
    with open(source, encoding="utf-8") as f:
        root = parse(f.read())
    main = root.first("main")
    pages = []
    for i, section in enumerate(main.find_all("section"), 1):
        title, subtitle = heading_parts(section.first("h2"))
        pages.append(Page(i, title, subtitle, section))
    files: dict = {}
    manifest = {"source": "docs/teaching/teaching-the-collection.html", "index": None, "pages": []}
    for p in pages:
        storage, markdown = p.storage(), p.markdown()
        files[f"pages/{p.slug}.xml"] = storage.encode("utf-8")
        files[f"markdown/{p.slug}.md"] = markdown.encode("utf-8")
        for name, data in p.files.items():
            files[f"attachments/{p.slug}/{name}"] = data
        manifest["pages"].append({
            "order": p.order, "title": p.title, "slug": p.slug, "storage": f"pages/{p.slug}.xml", "markdown": f"markdown/{p.slug}.md",
            "attachments": [f"attachments/{p.slug}/{name}" for name in p.files],
        })
    storage, markdown = index_page(root, pages)
    files["pages/index.xml"] = storage.encode("utf-8")
    files["markdown/index.md"] = markdown.encode("utf-8")
    manifest["index"] = {"title": INDEX_TITLE, "slug": "index", "storage": "pages/index.xml", "markdown": "markdown/index.md", "attachments": []}
    files["pages.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    validate(files)
    return manifest, files


def validate(files: dict) -> None:
    """Every page is well-formed XML in the two Confluence namespaces, references only attachments that exist, and carries no inline image."""
    import xml.etree.ElementTree as ET
    manifest = json.loads(files["pages.json"])
    for entry in [manifest["index"]] + manifest["pages"]:
        xml = files[entry["storage"]].decode("utf-8")
        if "data:image" in xml:
            raise ValueError(f"{entry['title']}: an inline image survived")
        wrapped = f'<root xmlns:ac="urn:ac" xmlns:ri="urn:ri">{xml.replace("&nbsp;", "&#160;")}</root>'
        try:
            tree = ET.fromstring(wrapped)
        except ET.ParseError as e:
            raise ValueError(f"{entry['title']}: storage format is not well-formed: {e}") from e
        referenced = {a.get("{urn:ri}filename") for a in tree.iter("{urn:ri}attachment")}
        have = {os.path.basename(a) for a in entry["attachments"]}
        if referenced - have:
            raise ValueError(f"{entry['title']}: image not attached: {sorted(referenced - have)}")
    titles = [p["title"] for p in manifest["pages"]] + [manifest["index"]["title"]]
    if len(set(titles)) != len(titles):
        raise ValueError("page titles are not unique")


def write(out: str, files: dict) -> None:
    for sub in ("pages", "markdown", "attachments"):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    for rel, data in files.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def check(out: str, files: dict) -> list:
    problems = []
    for rel, data in files.items():
        path = os.path.join(out, rel)
        if not os.path.exists(path):
            problems.append(f"missing: {rel}")
            continue
        with open(path, "rb") as f:
            if f.read() != data:
                problems.append(f"stale: {rel}")
    for sub in ("pages", "markdown", "attachments"):
        base = os.path.join(out, sub)
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                rel = os.path.relpath(os.path.join(dirpath, name), out)
                if rel not in files:
                    problems.append(f"unexpected: {rel}")
    return problems


def zip_tree(out: str, files: dict, dest: str) -> None:
    """The generated tree plus the uploader and its README, under one top-level directory."""
    import zipfile
    top = "teaching-confluence"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            z.writestr(f"{top}/{rel}", files[rel])
        for name in ("upload.py", "README.md"):
            z.write(os.path.join(out, name), f"{top}/{name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="refuse when the written tree differs from a fresh build")
    ap.add_argument("--zip", metavar="FILE", help="also write the tree, the uploader and the README as one zip")
    a = ap.parse_args(argv)
    manifest, files = build()
    if a.zip:
        os.makedirs(os.path.dirname(os.path.abspath(a.zip)), exist_ok=True)
        zip_tree(OUT, files, a.zip)
        print(f"wrote {a.zip}")
    if a.check:
        problems = check(a.out, files)
        if problems:
            print("confluence pages are stale; run python3 docs/teaching/build_confluence.py", file=sys.stderr)
            for p in problems[:20]:
                print("  " + p, file=sys.stderr)
            return 1
        print(f"ok: {len(manifest['pages'])} chapter pages current in {os.path.relpath(a.out)}")
        return 0
    write(a.out, files)
    n_att = sum(len(p["attachments"]) for p in manifest["pages"])
    print(f"wrote {len(manifest['pages'])} chapter pages, an index and {n_att} attachments to {os.path.relpath(a.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
