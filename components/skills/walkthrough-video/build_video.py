"""Frames + narration → MP4 with captions, plus a WebVTT track (in Python around ffmpeg).

Each slide is held for its narration plus PAD seconds; captions are the narration split into sentences and timed
proportionally across the slide ; they are burned into the video and also written as .vtt.
"""
from __future__ import annotations
import json, os, re, subprocess, shutil

PAD = 0.6
MIN_CUE = 1.2
OUT = os.environ.get("WALKTHROUGH_OUT", "out/walkthrough.mp4")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def sentences(t: str) -> list:
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+", t.strip()) if p.strip()]


def ts(s: float) -> str:
    h = int(s // 3600); m = int(s % 3600 // 60); sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def srt_ts(s: float) -> str:
    return ts(s).replace(".", ",")


def cues_for(text: str, start: float, length: float) -> list:
    ss = sentences(text); total = sum(len(x) for x in ss) or 1; t = start; out = []
    for x in ss:
        d = max(MIN_CUE, length * len(x) / total); out.append((t, min(t + d, start + length), x)); t += d
    return out


def main():
    os.makedirs("out", exist_ok=True); os.makedirs("build", exist_ok=True)
    slides = json.load(open("slides.json")); dur = json.load(open("narration/durations.json"))
    segs, t, vtt, srt, k = [], 0.0, ["WEBVTT", ""], [], 1
    for i, s in enumerate(slides, 1):
        d = dur[f"{i:02d}"]; length = d["seconds"] + PAD
        audio = os.path.join("narration", d["file"]); frame = f"frames/slide-{i:02d}.png"; seg = f"build/seg-{i:02d}.mp4"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-loop", "1", "-i", frame, "-i", audio, "-t", f"{length:.2f}", "-vf", "scale=1920:1080,format=yuv420p", "-r", "30",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-shortest", "-af", "apad", seg], check=True)
        segs.append(seg)
        for a, b, x in cues_for(s["narration"], t, length - PAD):
            vtt += [f"{ts(a)} --> {ts(b)}", x, ""]; srt += [str(k), f"{srt_ts(a)} --> {srt_ts(b)}", x, ""]; k += 1
        t += length
    open("build/concat.txt", "w").write("".join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    open(OUT.rsplit(".", 1)[0] + ".en.vtt", "w", encoding="utf-8").write("\n".join(vtt)); open("build/captions.srt", "w", encoding="utf-8").write("\n".join(srt))
    joined = "build/joined.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "build/concat.txt", "-c", "copy", joined], check=True)
    style = f"FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00202020,BackColour=&H80000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=28,Alignment=2"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", joined, "-vf", f"subtitles=build/captions.srt:fontsdir=/usr/share/fonts/truetype/dejavu:force_style='{style}'", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-c:a", "copy", OUT], check=True)
    shutil.copy(joined, OUT.rsplit(".", 1)[0] + ".nocaptions.mp4")
    print("video", OUT, f"{t:.1f}s", os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
