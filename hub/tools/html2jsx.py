#!/usr/bin/env python3
"""
Lossless HTML -> JSX transform for the CrossRiver AI Hub artboards.

The artboard markup is emitted by ux/lib.py + ux/hub.py and is already
JSX-shaped: every tag is either paired or explicitly self-closed, there are no
HTML entities, no void elements and no literal braces. So the only differences
between the artboard HTML and valid JSX are attribute *names* and the inline
`style` attribute's *type*.

This script rewrites exactly those, and nothing else, so the element tree and
every text node stay byte-identical to the published artboard.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXTRACT = os.path.join(ROOT, "extract")
SCREENS_DIR = os.path.join(ROOT, "src", "screens")

# Attribute names that differ between HTML and JSX. `aria-*` and `data-*` are
# passed through unchanged because React accepts them verbatim.
ATTR_RENAMES = {
    "class": "className",
    "for": "htmlFor",
    "tabindex": "tabIndex",
    "stroke-width": "strokeWidth",
    "stroke-linecap": "strokeLinecap",
    "stroke-linejoin": "strokeLinejoin",
    "stroke-dasharray": "strokeDasharray",
    "stroke-dashoffset": "strokeDashoffset",
    "stroke-opacity": "strokeOpacity",
    "fill-rule": "fillRule",
    "fill-opacity": "fillOpacity",
    "clip-rule": "clipRule",
    "clip-path": "clipPath",
    "stop-color": "stopColor",
    "stop-opacity": "stopOpacity",
    "text-anchor": "textAnchor",
    "font-family": "fontFamily",
    "font-size": "fontSize",
    "font-weight": "fontWeight",
    "letter-spacing": "letterSpacing",
    "marker-end": "markerEnd",
    "marker-start": "markerStart",
    "xlink:href": "xlinkHref",
    "colspan": "colSpan",
    "rowspan": "rowSpan",
    "srcset": "srcSet",
    "maxlength": "maxLength",
    "readonly": "readOnly",
    "autocomplete": "autoComplete",
    "contenteditable": "contentEditable",
    "spellcheck": "spellCheck",
    "enterkeyhint": "enterKeyHint",
    "inputmode": "inputMode",
    "crossorigin": "crossOrigin",
}

# HTML void elements, written as `<x>` in HTML but requiring `<x />` in JSX.
VOID = (
    "area base br col embed hr img input link meta param source track wbr"
).split()


def css_prop_to_js(prop: str) -> str:
    """`grid-template-columns` -> `gridTemplateColumns`; `-webkit-x` -> `WebkitX`."""
    prop = prop.strip()
    if prop.startswith("--"):
        return prop  # custom properties keep their exact name
    if prop.startswith("-"):
        prop = prop[1:]
        head, *rest = prop.split("-")
        return head[:1].upper() + head[1:] + "".join(p[:1].upper() + p[1:] for p in rest)
    head, *rest = prop.split("-")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def style_to_object(value: str) -> str:
    """`display:grid;gap:10px;` -> `{{display: 'grid', gap: '10px'}}`."""
    pairs = []
    for decl in value.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        if ":" not in decl:
            raise ValueError(f"style declaration without a colon: {decl!r}")
        prop, _, val = decl.partition(":")
        js_prop = css_prop_to_js(prop)
        val = val.strip()
        if "'" in val:
            raise ValueError(f"style value contains a quote: {val!r}")
        key = js_prop if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", js_prop) else f"'{js_prop}'"
        pairs.append(f"{key}: '{val}'")
    if not pairs:
        return "{{}}"
    return "{{" + ", ".join(pairs) + "}}"


ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
TAG_RE = re.compile(r"<([a-zA-Z][-a-zA-Z0-9]*)((?:\s+[^<>]*?)?)(/?)>")


def convert_tag(match: re.Match) -> str:
    name, attrs, selfclose = match.group(1), match.group(2), match.group(3)

    def convert_attr(m: re.Match) -> str:
        attr, value = m.group(1), m.group(2)
        if attr == "style":
            return f"style={style_to_object(value)}"
        jsx_attr = ATTR_RENAMES.get(attr, attr)
        return f'{jsx_attr}="{value}"'

    attrs = ATTR_RE.sub(convert_attr, attrs)
    if not selfclose and name.lower() in VOID:
        # `<br>` is valid HTML but not valid JSX; close it.
        return f"<{name}{attrs} />"
    # Whitespace inside the tag is preserved exactly, including the absence of a
    # space before a `/>`, so the emitted JSX stays byte-identical to the source.
    return f"<{name}{attrs}{selfclose}>"


def html_to_jsx(html: str) -> str:
    if "{" in html or "}" in html:
        raise ValueError("literal braces in markup need escaping; none expected here")
    if re.search(r"&[a-zA-Z#][a-zA-Z0-9]*;", html):
        raise ValueError("HTML entities in markup need review; none expected here")
    return TAG_RE.sub(convert_tag, html)


def component(name: str, jsx: str) -> str:
    indented = "\n".join(("      " + line) if line.strip() else line for line in jsx.split("\n"))
    return (
        "// GENERATED FILE - do not edit by hand.\n"
        "// Source: ux/%s.dc.html (design canvas artboard)\n"
        "// Regenerate with: python3 tools/html2jsx.py\n"
        "//\n"
        "// The element tree and every text node below are byte-identical to the\n"
        "// artboard. Only attribute names and the inline style type were rewritten.\n"
        "\n"
        "export default function %s() {\n"
        "  return (\n"
        "    <>\n"
        "%s\n"
        "    </>\n"
        "  );\n"
        "}\n"
    ) % (name, name, indented)


def main() -> int:
    meta = json.load(open(os.path.join(EXTRACT, "meta.json")))
    os.makedirs(SCREENS_DIR, exist_ok=True)
    # Screens rebuilt as live, stateful components keep the artboard only as the
    # pixel reference; they are not regenerated over.
    LIVE = {"HubIntake", "HubHome", "HubListing", "HubWorkspace", "HubAssistant"}
    for name in meta:
        if name in LIVE:
            continue
        html = open(os.path.join(EXTRACT, f"{name}.body.html")).read().strip()
        jsx = html_to_jsx(html)
        # Round-trip check: undoing the rewrite must return the original bytes.
        back = jsx
        for html_attr, jsx_attr in ATTR_RENAMES.items():
            back = re.sub(rf'\b{re.escape(jsx_attr)}="', f'{html_attr}="', back)
        back = re.sub(r"style=\{\{[^}]*\}\}", "style=\x00", back)
        expect = re.sub(r'style="[^"]*"', "style=\x00", html)
        if back != expect:
            print(f"  !! round-trip mismatch on {name}", file=sys.stderr)
            return 1
        path = os.path.join(SCREENS_DIR, f"{name}.tsx")
        open(path, "w").write(component(name, jsx))
        print(f"  {name:<14} {len(html):>6} bytes html -> {len(jsx):>6} bytes jsx  (tree verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
