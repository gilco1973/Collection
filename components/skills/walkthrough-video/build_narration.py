"""Narration for each slide: one audio file per slide plus its duration, from narration/slideNN.txt (written by deck.py).

Providers, chosen by --provider or the first that works:
  elevenlabs  ELEVENLABS_API_KEY in the environment (voice Daniel by default)
  edge        Microsoft Edge neural voices through the edge-tts package (no key; needs egress to speech.platform.bing.com)
  captions    no voice: a silent track timed by reading speed (2.6 words per second) so the video still plays with captions

Writes narration/slideNN.mp3 (or .wav for captions) and narration/durations.json. Selective regeneration: pass slide numbers.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, urllib.request

WPS = 2.6
ELEVEN_VOICE = os.environ.get("ELEVEN_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")  # Daniel


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def duration_of(path: str) -> float:
    out = subprocess.run([ffmpeg(), "-i", path], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":"); return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError("no duration for " + path)


def eleven(text: str, out: str):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key: raise RuntimeError("ELEVENLABS_API_KEY is not set")
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}", data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r: open(out, "wb").write(r.read())


def edge(text: str, out: str):
    import asyncio, edge_tts
    async def go(): await edge_tts.Communicate(text, os.environ.get("EDGE_VOICE", "en-US-AriaNeural")).save(out)
    asyncio.run(go())
    if os.path.getsize(out) == 0: raise RuntimeError("edge-tts produced no audio")


def captions(text: str, out: str):
    secs = max(3.0, len(text.split()) / WPS + 0.8)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{secs:.2f}", "-q:a", "9", out], check=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("slides", nargs="*", type=int); ap.add_argument("--provider", choices=["elevenlabs", "edge", "captions"], default=None)
    a = ap.parse_args()
    files = sorted(f for f in os.listdir("narration") if f.startswith("slide") and f.endswith(".txt"))
    durations = json.load(open("narration/durations.json")) if os.path.exists("narration/durations.json") else {}
    order = [a.provider] if a.provider else ["elevenlabs", "edge", "captions"]
    used = None
    for f in files:
        n = int(f[5:7])
        if a.slides and n not in a.slides: continue
        text = open(os.path.join("narration", f), encoding="utf-8").read().strip()
        for prov in order:
            out = os.path.join("narration", f"slide{n:02d}." + ("wav" if prov == "captions" else "mp3"))
            try:
                {"elevenlabs": eleven, "edge": edge, "captions": captions}[prov](text, out)
                for other in ("mp3", "wav"):
                    p2 = os.path.join("narration", f"slide{n:02d}.{other}")
                    if p2 != out and os.path.exists(p2): os.remove(p2)
                durations[f"{n:02d}"] = {"file": os.path.basename(out), "seconds": round(duration_of(out), 2), "provider": prov, "words": len(text.split())}
                used = prov; print(f"slide {n:02d}: {prov} {durations[f'{n:02d}']['seconds']}s"); break
            except Exception as e:  # try the next provider
                print(f"slide {n:02d}: {prov} failed ({type(e).__name__}: {str(e)[:80]})", file=sys.stderr)
        else:
            sys.exit(f"slide {n:02d}: no provider worked")
    json.dump(durations, open("narration/durations.json", "w"), indent=1)
    print("provider used:", used)


if __name__ == "__main__":
    main()
