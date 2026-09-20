"""Live example: two renders that differ in one region, diffed the way the gate diffs them; no browser needed.
Draws a reference and a candidate PNG with the standard library (zlib), runs diff.py's core on them, and prints the count."""
import json, os, struct, subprocess, sys, tempfile, zlib

def png(path, w, h, pixel):
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

with tempfile.TemporaryDirectory() as d:
    cmp = os.path.join(d, "compare"); os.makedirs(cmp)
    png(os.path.join(cmp, "Home.ref.png"), 120, 80, lambda x, y: (240, 244, 248))
    png(os.path.join(cmp, "Home.app.png"), 120, 80, lambda x, y: (220, 20, 20) if 30 <= x < 50 and 20 <= y < 30 else (240, 244, 248))
    json.dump([{"name": "Home", "route": "/", "artboard": "Home.html", "height": 80}], open(os.path.join(d, "screens.json"), "w"))
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed, so diff.py cannot run here; the two PNGs were written to", cmp); print("install: python3 -m pip install pillow"); sys.exit(0)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "diff.py")], cwd=d, env={**os.environ, "OUT": cmp, "SCREENS": os.path.join(d, "screens.json")}, capture_output=True, text=True)
    print(r.stdout.strip()); print("exit code", r.returncode, "(2 means the gate would fail: 200 pixels differ, as drawn)")
