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
WINDOWS = os.name == "nt"
# one environment with numpy (mix.py) and faster-whisper (cut.py)
VENV = os.path.expanduser(os.environ.get("YT_VENV", "~/.local/share/yt-publisher/venv"))
PYTHON = os.path.join(VENV, "Scripts", "python.exe") if WINDOWS else os.path.join(VENV, "bin", "python")
BLENDER = os.environ.get("BLENDER") or shutil.which("blender") or os.path.expanduser(
    r"~\BlenderPortable53\blender-5.3.0-windows-x64\blender.exe")
os.environ.setdefault("PYTHONUTF8", "1")  # the scripts it starts read and write UTF-8, also on Windows
VOICES = {"mina": "Aoede", "stamp": "Algenib", "lumi": "Puck"}  # voices of gemini.py, which also says how they act

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="environment: GEMINI_API_KEY, or in .env (see gemini.py), only to make new voices.\n"
           "Needs ffmpeg, Blender (BLENDER, else on PATH, else the portable 5.3 in your home on Windows),\n"
           "and an environment with numpy and faster-whisper (YT_VENV, default ~/.local/share/yt-publisher/venv).\n\nexample:\n"
           "  python3 videos/episode.py videos/episodes/ep0.json --out ~/Videos/yt-publisher")
p.add_argument("episode", help="JSON of the episode")
p.add_argument("--out", default=".", help="directory of the MP4 (default: current)")
p.add_argument("--until", choices=["voices", "mix", "frames", "mp4"], default="mp4", help="last step (default: mp4)")
p.add_argument("--at", nargs="+", metavar="SECONDS", help="only render the frames at these times, to check the shots")
p.add_argument("--scale", default="67", help="percent of 1080x1920 (default: 67)")
p.add_argument("--draft", action="store_true", help="quick look: small, 8 frames per second, in OUT/drafts/EPISODE-draft.mp4")
A = p.parse_args()
if A.draft:
    A.scale = "34"
STEP, SAMPLES = ("3", "4") if A.draft else ("1", "16")


def available():
    """Gigabytes of memory available."""
    if WINDOWS:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("total", "free", "pagefile", "freepagefile", "virtual", "freevirtual", "extended")]

        s = Status()
        s.length = ctypes.sizeof(s)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return s.free / 1e9
    with open("/proc/meminfo") as f:
        return int(next(line for line in f if line.startswith("MemAvailable")).split()[1]) / 1e6


def run(*cmd, cap=None, cwd=None, feed=None):
    free = available()
    if free < 2.5:
        sys.exit(f"only {free:.1f} GB of memory available, not starting: {cmd[0]}")
    if cap and shutil.which("systemd-run"):
        cmd = ("systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={cap}", "-p", "MemorySwapMax=0", *cmd)
    if feed:  # bytes for its standard input
        done = subprocess.run(cmd, input=feed, capture_output=True, cwd=cwd)
        done.stdout, done.stderr = (s.decode(errors="replace") for s in (done.stdout, done.stderr))
    else:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if done.returncode:
        sys.exit(f"{' '.join(cmd)}\n{(done.stdout + done.stderr)[-2000:]}")
    return done.stdout


def step(name):
    if A.until == name:
        sys.exit(0)


with open(A.episode, encoding="utf-8") as f:
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
    """Whether line n must be said again: no sound yet, or another voice or text. Never when dub.py has a take of it."""
    if dubbed(n):
        return False
    mark = wav(n) + ".txt"
    return not (os.path.exists(wav(n)) and os.path.exists(mark) and open(mark).read() == text)


texts = [line["text"] for line in EP["lines"]]
for who, voice in VOICES.items():
    mine = [n for n, line in enumerate(EP["lines"]) if line["who"] == who]
    if not any(stale(n, f"{voice}: {texts[n]}") for n in mine):
        continue
    # one take for all the lines of a character, so that it keeps one intonation; another text is another take
    takes = f"{work}/gemini-{hashlib.sha256(repr([texts[n] for n in mine]).encode()).hexdigest()[:8]}"
    run(sys.executable, f"{HERE}/gemini.py", A.episode, "--only", who, "--voices", voice, "--out", takes)
    print(run(PYTHON, "-W", "ignore", f"{HERE}/cut.py", f"{takes}/{who}-{voice}.wav", "--lines", *(texts[n] for n in mine),
              "--out", *(wav(n) for n in mine), cap="2G").strip(), flush=True)
    for n in mine:
        with open(wav(n) + ".txt", "w") as f:
            f.write(f"{voice}: {texts[n]}")
print("voices: done", flush=True)
step("voices")
print("mix:", run(PYTHON,f"{HERE}/mix.py", "--episode", A.episode, "--dir", work, "--dub", dub).strip(), flush=True)
step("mix")

key = hashlib.sha256()
for path in (f"{work}/timeline.json", f"{HERE}/scene.py", f"{HERE}/characters.py"):
    with open(path, "rb") as f:
        key.update(f.read())
frames = f"{work}/frames-{key.hexdigest()[:8]}-{A.scale}{'-draft' * A.draft}"  # a change of scene or timing renders again
# opengl: Blender 5.3 can crash in the shader compiler of Vulkan
blender = [BLENDER, "-b", "--gpu-backend", "opengl", "--python-exit-code", "1", "-P", f"{HERE}/scene.py", "--", "--timeline",
           f"{work}/timeline.json", "--scale", A.scale, "--step", STEP, "--samples", SAMPLES, "--out"]
if A.at:
    run(*blender, f"{work}/check", "--at", *A.at)
    print(f"frames to check: {work}/check")
    sys.exit(0)
for image in os.listdir(frames) if os.path.isdir(frames) else []:
    with open(f"{frames}/{image}", "rb") as f:
        whole = f.read().endswith(b"IEND\xaeB`\x82")
    if not whole:  # the machine stopped while it was written, and scene.py skips the images that exist
        os.remove(f"{frames}/{image}")
print("frames:", run(*blender, frames).strip().splitlines()[-3:], flush=True)
step("frames")
with open(f"{work}/timeline.json", encoding="utf-8") as f:
    T = json.load(f)
folder = os.path.join(A.out, "drafts") if A.draft else A.out
os.makedirs(folder, exist_ok=True)
mp4 = os.path.abspath(os.path.join(folder, f"{name}{'-draft' * A.draft}.mp4"))
images = b""  # the frames, in order, through a pipe: the ffmpeg of Windows has no glob
for image in sorted(os.listdir(frames)):
    if image.endswith(".png"):
        with open(f"{frames}/{image}", "rb") as f:
            images += f.read()
# from the work directory, so that the filter reads captions.ass without a drive letter; Inter-Bold.ttf from here,
# as Inter is not installed everywhere
fonts = os.path.relpath(HERE, work).replace(os.sep, "/")
run("ffmpeg", "-loglevel", "error", "-y", "-framerate", str(T["fps"] // int(STEP)), "-f", "image2pipe", "-c:v", "png", "-i", "-",
    "-i", "mix.wav",
    "-vf", f"fps={T['fps']},ass=captions.ass:fontsdir={fonts},fade=out:st={T['cut']}:d=0.04,scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-af", "loudnorm=I=-14:TP=-1.5", "-ar", "48000", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "4",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", mp4, cwd=work, feed=images)
print(mp4)
