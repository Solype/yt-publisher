#!/usr/bin/env python3
"""Make an episode from its JSON: voices, sound, frames, then the MP4. Every step skips what is already made.
The takes of dub.py, in OUT/EPISODE-dub, replace the voices they dub."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARE = os.path.expanduser("~/.local/share")
KOKORO, CHATTERBOX = f"{SHARE}/kokoro/venv/bin/python", f"{SHARE}/chatterbox/venv/bin/python"
VOICES = {"stamp": 9, "lumi": 6}  # numbers in voices.py; Mina is played by acting.py
MINA = f"{SHARE}/chatterbox/bella.wav"

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="No environment variable. Needs ffmpeg, Blender, Kokoro and Chatterbox (see voices.py and acting.py), and\n"
           f"the voice Mina imitates in {MINA}.\n\nexample:\n"
           "  python3 videos/episode.py videos/episodes/ep0.json --out ~/Videos/yt-publisher")
p.add_argument("episode", help="JSON of the episode")
p.add_argument("--out", default=".", help="directory of the MP4 (default: current)")
p.add_argument("--until", choices=["voices", "mix", "frames", "mp4"], default="mp4", help="last step (default: mp4)")
p.add_argument("--at", nargs="+", metavar="SECONDS", help="only render the frames at these times, to check the shots")
p.add_argument("--scale", default="67", help="percent of 1080x1920 (default: 67)")
A = p.parse_args()


def run(*cmd, cap=None):
    with open("/proc/meminfo") as f:
        free = int(next(line for line in f if line.startswith("MemAvailable")).split()[1]) / 1e6
    if free < 2.5:
        sys.exit(f"only {free:.1f} GB of memory available, not starting: {cmd[0]}")
    if cap:
        cmd = ("systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={cap}", "-p", "MemorySwapMax=0", *cmd)
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        sys.exit(f"{' '.join(cmd)}\n{(done.stdout + done.stderr)[-2000:]}")
    return done.stdout


def step(name):
    if A.until == name:
        sys.exit(0)


with open(A.episode) as f:
    EP = json.load(f)
name = os.path.splitext(os.path.basename(A.episode))[0]
work = os.path.expanduser(f"~/.cache/yt-publisher/{name}")
os.makedirs(work, exist_ok=True)


dub = os.path.join(A.out, f"{name}-dub")


def dubbed(n):
    return os.path.exists(f"{dub}/{n:02}.wav")


def wav(n):
    return f"{work}/{n:02}.wav"


def stale(n, text):
    """Whether line n must be said again: no sound yet, or another text. Never when dub.py has a take of it."""
    if dubbed(n):
        return False
    mark = wav(n) + ".txt"
    return not (os.path.exists(wav(n)) and os.path.exists(mark) and open(mark).read() == text)


def keep(source, n, text):
    shutil.move(source, wav(n))
    with open(wav(n) + ".txt", "w") as f:
        f.write(text)


texts = [line["text"] for line in EP["lines"]]
for n, line in enumerate(EP["lines"]):
    who = line["who"]
    if who in VOICES and stale(n, texts[n]):
        run(KOKORO, f"{HERE}/voices.py", "--only", who, "--voice", str(VOICES[who]), "--say", texts[n], "--out", work, cap="2G")
        keep(f"{work}/{who}-line.wav", n, texts[n])
for take in EP.get("mina_takes", []):
    if any(stale(n, texts[n]) for n in take):
        out = run(CHATTERBOX, "-W", "ignore", f"{HERE}/acting.py", "--ref", MINA, "--out", work, "--say",
                  " ".join(texts[n] for n in take), "--cut", *(str(len(texts[n].split())) for n in take), cap="5G")
        print("\n".join(s for s in out.splitlines() if "try" in s or "clean" in s), flush=True)
        for k, n in enumerate(take):
            keep(f"{work}/bella-acted-{k}.wav", n, texts[n])
print("voices: done", flush=True)
step("voices")
print("mix:", run(KOKORO, f"{HERE}/mix.py", "--episode", A.episode, "--dir", work, "--dub", dub).strip(), flush=True)
step("mix")

key = hashlib.sha256()
for path in (f"{work}/timeline.json", f"{HERE}/scene.py", f"{HERE}/characters.py"):
    with open(path, "rb") as f:
        key.update(f.read())
frames = f"{work}/frames-{key.hexdigest()[:8]}-{A.scale}"  # a change of scene or timing renders again
blender = ["blender", "-b", "--python-exit-code", "1", "-P", f"{HERE}/scene.py", "--", "--timeline",
           f"{work}/timeline.json", "--scale", A.scale, "--out"]
if A.at:
    run(*blender, f"{work}/check", "--at", *A.at)
    print(f"frames to check: {work}/check")
    sys.exit(0)
print("frames:", run(*blender, frames).strip().splitlines()[-3:], flush=True)
step("frames")
with open(f"{work}/timeline.json") as f:
    T = json.load(f)
os.makedirs(A.out, exist_ok=True)
mp4 = os.path.join(A.out, f"{name}.mp4")
run("ffmpeg", "-loglevel", "error", "-y", "-framerate", str(T["fps"]), "-i", f"{frames}/%04d.png", "-i", f"{work}/mix.wav",
    "-vf", f"ass={work}/captions.ass,fade=out:st={T['cut']}:d=0.04,scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-af", "loudnorm=I=-14:TP=-1.5", "-ar", "48000", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "4",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", mp4)
print(mp4)
