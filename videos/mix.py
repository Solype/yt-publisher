#!/usr/bin/env python3
"""Sound of an episode: lines, stamp blows, chime and drone, with its timeline and its subtitles."""
import argparse
import json
import os
import re
import wave

SR, FPS = 48000, 24

parser = argparse.ArgumentParser(
    description=__doc__, epilog="No environment variable. Needs numpy; every WAV is 48 kHz, 16-bit, mono.\n\n"
    "example:\n  python3 videos/mix.py --episode videos/episodes/ep0.json --dir work\n\n"
    "reads  00.wav 01.wav ... (one per line of the episode) in --dir\n"
    "writes mix.wav timeline.json captions.ass in --dir",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dir", default=".", help="directory of the lines, and of the results (default: current)")
parser.add_argument("--dub", metavar="DIR", help="takes of dub.py: NN.wav and NN.json, each in place of the line NN")
parser.add_argument("--episode", required=True, help="JSON of the episode (format: videos/episodes/ep0.json)")
ARGS = parser.parse_args()
with open(ARGS.episode) as f:
    EP = json.load(f)

import numpy as np  # noqa: E402  (after --help)


def load(name, folder):
    with wave.open(os.path.join(folder, name + ".wav")) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 1, 2), name
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768


def trim(x, floor=.01):
    """The sound without its silent ends, and the seconds cut before it."""
    on = np.flatnonzero(np.abs(x) > floor)
    if not len(on):
        raise SystemExit("a take is silent")
    first = max(0, on[0] - SR // 100)
    return x[first:on[-1] + SR // 25], first / SR


def line_sound(n):
    """Its sound, and when it starts if it was dubbed (else None)."""
    name = f"{n:02}"
    if not ARGS.dub or not os.path.exists(os.path.join(ARGS.dub, name + ".wav")):
        return trim(load(name, ARGS.dir))[0], None
    x = load(name, ARGS.dub)
    x, skipped = trim(x, max(.01, .06 * np.abs(x).max()))  # a microphone is never silent
    with open(os.path.join(ARGS.dub, name + ".json")) as f:
        return x, json.load(f)["at"] + skipped


def even(x):
    """Same loudness for every line, measured on its loud half."""
    frames = np.sqrt((x[:len(x) // 480 * 480].reshape(-1, 480) ** 2).mean(1))
    return x * .13 / frames[frames > np.median(frames)].mean()


def blow():
    """The stamp: a falling thump, a wooden knock and a short click."""
    t = np.arange(int(.6 * SR)) / SR
    noise = np.random.default_rng(3).normal(size=len(t))
    thump = np.sin(2 * np.pi * (48 * t + 70 * (1 - np.exp(-18 * t)) / 18)) * np.exp(-9 * t)
    knock = np.sin(2 * np.pi * 390 * t) * np.exp(-45 * t) + .6 * np.sin(2 * np.pi * 730 * t) * np.exp(-60 * t)
    return np.tanh(1.5 * (.8 * thump + .35 * knock + .25 * noise * np.exp(-110 * t)))


def drone(n):
    t = np.arange(n) / SR
    low = sum(a * np.sin(2 * np.pi * f * t + .6 * np.sin(2 * np.pi * r * t))
              for f, a, r in ((55, .6, .11), (82.4, .4, .17), (110, .5, .07), (164.8, .22, .13), (220, .12, .19)))
    return low * (.85 + .15 * np.sin(2 * np.pi * .23 * t))


def chime():
    t = np.arange(int(1.2 * SR)) / SR
    return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-d * t) for f, a, d in ((1318, .5, 4), (1975, .3, 5), (2637, .15, 7)))


now, lines, voice = EP["lead"], [], []
for n, line in enumerate(EP["lines"]):
    x, at = line_sound(n)
    x = even(x)
    now = now + line["before"] if at is None else max(at, now if n else 0)
    lines.append({"who": line["who"], "text": line["text"], "start": round(now, 3), "end": round(now + len(x) / SR, 3)})
    voice.append((now, x))
    now += len(x) / SR
cut = now + EP["tail"]
total = cut + EP.get("black", 0)


def when(v):
    """A time: seconds, or s2-.1 (line 2 starts, minus .1 s), m2 (its middle), e2+.3 (its end); lists are walked."""
    if isinstance(v, list):
        return [when(i) for i in v]
    m = re.fullmatch(r"([sme])(\d+)([+-][\d.]+)?", v) if isinstance(v, str) else None
    if not m:
        return v
    line = lines[int(m[2])]
    at = {"s": line["start"], "e": line["end"], "m": (line["start"] + line["end"]) / 2}[m[1]]
    return round(at + float(m[3] or 0), 3)


cues = {k: when(v) for k, v in EP["cues"].items()}
mix = drone(int(total * SR))
mix *= .03 / np.sqrt((mix ** 2).mean())
mix[:SR // 2] *= np.linspace(0, 1, SR // 2)
for at, x in voice + [(b, .55 * blow()) for b in cues.get("bams", [])] + [(b, .12 * chime()) for b in cues.get("chimes", [])]:
    i = int(at * SR)
    mix[i:i + len(x)] += x[:len(mix) - i]
mix[int(cut * SR):] = 0
mix[int(cut * SR) - 480:int(cut * SR)] *= np.linspace(1, 0, 480)
level = {w: [0.0] * (int(total * FPS) + 1) for w in ("mina", "stamp", "lumi")}
for line, (at, x) in zip(lines, voice):
    for k in range(int(at * FPS), int((at + len(x) / SR) * FPS) + 1):
        a = max(0, int((k / FPS - at) * SR))
        part = x[a:a + SR // FPS]
        if len(part) and k < len(level[line["who"]]):
            level[line["who"]][k] = round(float(min(1, np.sqrt((part ** 2).mean()) / .18)), 3)
with wave.open(os.path.join(ARGS.dir, "mix.wav"), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((np.tanh(mix * 1.2) * 32000).astype(np.int16).tobytes())
with open(os.path.join(ARGS.dir, "timeline.json"), "w") as f:
    json.dump({"fps": FPS, "duration": total, "cut": cut, "lines": lines, "level": level, **cues}, f)


def stamp_time(t):
    return f"{int(t // 3600)}:{int(t // 60) % 60:02}:{t % 60:05.2f}"


with open(os.path.join(ARGS.dir, "captions.ass"), "w") as f:
    f.write("[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, "
            "PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
            "MarginV\nStyle: s,Inter,64,&H00F4F7F8,&H00140A08,&H00000000,0,1,3,0,8,90,90,88\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Text\n")
    for n, line in enumerate(lines):
        end = min(line["end"] + .25, lines[n + 1]["start"]) if n + 1 < len(lines) else line["end"] + .4
        f.write(f"Dialogue: 0,{stamp_time(line['start'])},{stamp_time(end)},s,{{\\fad(60,60)}}{line['text']}\n")
print(f"{total:.1f} s, " + ", ".join(f"{li['who']} {li['start']:.1f}-{li['end']:.1f}" for li in lines))
