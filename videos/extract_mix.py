#!/usr/bin/env python3
"""Sound of the extract: lines, stamp blow and low drone, with the timeline and the subtitles that go with it."""
import argparse
import json
import os
import wave

# (who, file, subtitle, silence before in s); Mina's file is cut on its silences, a line is one or several pieces
SCRIPT = [("stamp", "stamp1", "Refused.", .0), ("mina", (1, 2), "Refused? What do you mean, refused?!", .18),
          ("stamp", "stamp2", "Line six, column five.", .12), ("mina", (0,), "But I gave it a number!", .15),
          ("lumi", "lumi1", "It wants two. You gave one.", .25), ("mina", (3,), "Okay, okay! How about now?", .2),
          ("stamp", "stamp3", "Accepted. Next!", .55)]
SR, FPS = 48000, 24

parser = argparse.ArgumentParser(
    description=__doc__, epilog="No environment variable. Needs numpy; every WAV is 48 kHz, 16-bit, mono.\n\n"
    "example:\n  python3 videos/extract_mix.py --dir extract\n\n"
    "reads  stamp1.wav stamp2.wav stamp3.wav lumi1.wav mina.wav in --dir\n"
    "writes mix.wav timeline.json captions.ass in --dir",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dir", default=".", help="directory of the lines, and of the results (default: current)")
ARGS = parser.parse_args()

import numpy as np  # noqa: E402  (after --help)


def load(name):
    with wave.open(os.path.join(ARGS.dir, name + ".wav")) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 1, 2), name
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768


def trim(x):
    on = np.flatnonzero(np.abs(x) > .01)
    return x[max(0, on[0] - SR // 100):on[-1] + SR // 25]


def split(x, gap=.55):
    """The lines of a file, separated by at least gap seconds of silence."""
    on = np.flatnonzero(np.abs(x) > .004)
    cuts = np.flatnonzero(np.diff(on) > gap * SR)
    return [trim(x[a:b + 1]) for a, b in zip(on[np.r_[0, cuts + 1]], on[np.r_[cuts, len(on) - 1]])]


def join(pieces, numbers, pause=.4):
    out = [pieces[numbers[0]]]
    for n in numbers[1:]:
        out += [np.zeros(int(pause * SR)), pieces[n]]
    return np.concatenate(out)


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


mina = split(load("mina"))
assert len(mina) == 4, f"expected 4 pieces of Mina, found {len(mina)}"
now, lines, voice = .85, [], []
for who, source, text, before in SCRIPT:
    x = even(join(mina, source) if who == "mina" else trim(load(source)))
    now += before
    lines.append({"who": who, "text": text, "start": round(now, 3), "end": round(now + len(x) / SR, 3)})
    voice.append((now, x))
    now += len(x) / SR
total = now + .7
bams = [lines[0]["start"] - .3, lines[-1]["start"] - .3]
mix = drone(int(total * SR))
mix *= .03 / np.sqrt((mix ** 2).mean())
mix[:SR // 2] *= np.linspace(0, 1, SR // 2)
mix[-SR // 2:] *= np.linspace(1, 0, SR // 2)
for at, x in voice + [(b, .55 * blow()) for b in bams]:
    i = int(at * SR)
    mix[i:i + len(x)] += x[:len(mix) - i]
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
    json.dump({"fps": FPS, "duration": total, "lines": lines, "bams": bams, "level": level}, f)


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
