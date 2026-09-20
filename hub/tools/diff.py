#!/usr/bin/env python3
"""Pixel-diff each <Screen>.ref.png against <Screen>.app.png in ./compare.

Prints differing-pixel counts and writes <Screen>.diff.png with differences
highlighted in red over a faded copy of the reference, so a mismatch can be
located by eye.
"""
import json
import os
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMP = os.path.join(ROOT, "compare")
SCREENS = ["HubHome", "HubListing", "HubIntake", "HubWorkspace", "HubAssistant"]

# Documented, intentional deviations (state the artboards disagree on among
# themselves); pixels inside these boxes are reported but not counted.
EXPECTED = {}
_exp = os.path.join(CMP, "expected.json")
if os.path.exists(_exp):
    EXPECTED = {k: v for k, v in json.load(open(_exp)).items() if not k.startswith("_")}

results = {}
worst = 0.0
for name in SCREENS:
    a = Image.open(os.path.join(CMP, f"{name}.ref.png")).convert("RGB")
    b = Image.open(os.path.join(CMP, f"{name}.app.png")).convert("RGB")
    if a.size != b.size:
        print(f"{name:<13} SIZE MISMATCH ref={a.size} app={b.size}")
        results[name] = {"size_mismatch": True, "ref": a.size, "app": b.size}
        worst = 100.0
        continue
    d = ImageChops.difference(a, b)
    mask = d.convert("L").point(lambda v: 255 if v > 0 else 0)
    allowed = 0
    for region in EXPECTED.get(name, []):
        x0, y0, x1, y1 = region["box"]
        sub = mask.crop((x0, y0, x1, y1))
        allowed += sub.histogram()[255]
        mask.paste(0, (x0, y0, x1, y1))
    hist = mask.histogram()
    differing = hist[255]
    total = a.size[0] * a.size[1]
    pct = 100.0 * differing / total
    bbox = mask.getbbox()
    worst = max(worst, pct)
    results[name] = {"differing_px": differing, "total_px": total, "pct": round(pct, 4), "bbox": bbox, "allowed_px": allowed}
    # Visual diff: faded reference with differences in red.
    faded = Image.blend(a, Image.new("RGB", a.size, (255, 255, 255)), 0.6)
    red = Image.new("RGB", a.size, (220, 20, 20))
    out = Image.composite(red, faded, mask)
    out.save(os.path.join(CMP, f"{name}.diff.png"))
    note = f"  (+{allowed} px inside documented regions, see compare/expected.json)" if allowed else ""
    print(f"{name:<13} {differing:>8} / {total:>8} px differ  ({pct:6.3f}%)  bbox={bbox}{note}")

json.dump(results, open(os.path.join(CMP, "results.json"), "w"), indent=2)
print(f"\nworst screen: {worst:.3f}% differing pixels")
sys.exit(0 if worst == 0 else 2)
