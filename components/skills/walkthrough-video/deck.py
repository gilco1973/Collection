"""The walkthrough deck: slides with narration, loaded from a plan file. The SLIDES list in the plan is the
authoritative source: the deck HTML, the narration files, the captions and the timing all derive from it.

    python3 deck.py slides.py        # writes deck.html, narration/slideNN.txt, slides.json

A plan file defines TITLE, FOOT and SLIDES = [(id, kicker, title, [bullets], shot_or_None, narration), ...]; slides
whose id is in the plan's optional DARK tuple render as full-bleed title cards; every slide is light otherwise.
`example_slides.py` is a five-slide example.
"""
from __future__ import annotations
import html, importlib.util, json, os, sys

W, H = 1280, 720

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap');
*{box-sizing:border-box}body{margin:0;background:#111}
.slide{width:1280px;height:720px;position:relative;overflow:hidden;background:#f4f6f8;color:#1b2430;font-family:'IBM Plex Sans',system-ui,sans-serif;page-break-after:always}
.slide.dark{background:#1b2430;color:#f4f6f8}
.k{position:absolute;left:64px;top:44px;font:600 13px/1 'IBM Plex Sans Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#8a4f1d}.dark .k{color:#e0b98a}
h1{position:absolute;left:64px;top:70px;margin:0;font:600 34px/1.2 'IBM Plex Sans',sans-serif;width:1150px;text-wrap:balance}
.dark h1{font-size:48px;top:200px;width:1000px}
ul{position:absolute;left:64px;top:150px;margin:0;padding:0;list-style:none;width:440px;font-size:17px;line-height:1.45}
ul li{margin:0 0 14px;padding-left:18px;position:relative}ul li:before{content:'';position:absolute;left:0;top:10px;width:8px;height:8px;border-radius:50%;background:#8a4f1d}
.dark ul,.dark.noshot ul{top:330px;width:1000px;font-size:22px}.dark ul li:before{background:#e0b98a}
.shot{position:absolute;right:48px;top:130px;width:700px;height:470px;border-radius:10px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.18);background:#fff;border:1px solid #d5dbe3}
.shot img{width:100%;display:block;object-fit:cover;object-position:top;height:100%}
.noshot ul{width:1150px;font-size:21px;top:160px}
.foot{position:absolute;left:64px;bottom:30px;font-size:12px;color:#5b687a}.dark .foot{color:#a3adba}
.n{position:absolute;right:64px;bottom:30px;font-size:12px;color:#5b687a}
"""


def load(path: str):
    spec = importlib.util.spec_from_file_location("slides", path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def build(plan, out_html: str = "deck.html", narration_dir: str = "narration"):
    SLIDES, TITLE, FOOT, DARK = plan.SLIDES, plan.TITLE, plan.FOOT, tuple(getattr(plan, "DARK", ()))
    os.makedirs(narration_dir, exist_ok=True)
    parts = []
    for i, (sid, kicker, title, bullets, shot, narration) in enumerate(SLIDES, 1):
        dark = sid in DARK
        cls = "slide" + (" dark" if dark else "") + ("" if shot else " noshot")
        lis = "".join(f"<li>{html.escape(b)}</li>" for b in bullets)
        img = f'<div class="shot"><img src="shots/{shot}" alt=""></div>' if shot else ""
        parts.append(f'<section class="{cls}" id="s{i:02d}"><div class="k">{html.escape(kicker)}</div><h1>{html.escape(title)}</h1><ul>{lis}</ul>{img}<div class="foot">{html.escape(FOOT)}</div><div class="n">{i} / {len(SLIDES)}</div></section>')
        with open(os.path.join(narration_dir, f"slide{i:02d}.txt"), "w", encoding="utf-8") as f:
            f.write(narration + "\n")
    open(out_html, "w", encoding="utf-8").write(f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(TITLE)}</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>")
    json.dump([{"id": s[0], "title": s[2], "narration": s[5], "shot": s[4]} for s in SLIDES], open("slides.json", "w"), indent=1)
    print("deck", len(SLIDES), "slides")


if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(__doc__)
    build(load(sys.argv[1]))
