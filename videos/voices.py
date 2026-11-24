#!/usr/bin/env python3
"""Voice auditions of the compiler series: several local Kokoro voices per character."""
import argparse
import os
import subprocess
import sys
import tempfile
import wave

KOKORO = os.path.expanduser("~/.local/share/kokoro")
LINES = {
    "mina": ["But... I gave it a number!", "Refused? What do you mean, refused?!", "Okay, okay. How about now?"],
    "stamp": ["Refused.", "Line six, column five.", "No function add takes one integer. Next!"],
    "lumi": ["It wants two. You gave one.", "Add needs two integers, and Stamp counts them.",
             "See the empty slot? That is all Stamp is saying."],
}
# (Kokoro voice, speed, robot effect)
VOICES = {
    "mina": [("af_heart", 1.1, None), ("af_bella", 1.1, None), ("af_jessica", 1.1, None), ("af_sky", 1.1, None)],
    "stamp": [("am_michael", 1.0, "monotone"), ("am_onyx", 1.1, "metal"), ("bm_lewis", 1.0, "ring"),
              ("am_fenrir", 1.0, "radio"), ("am_onyx", 1.05, "metal92"), ("am_onyx", 1.0, "metal98"),
              ("am_onyx", .95, "metal104"), ("am_adam", 1.05, "chorus"), ("bm_george", 1.0, "speaker"),
              ("am_eric", 1.05, "half120"), ("bm_daniel", 1.0, "metal100"), ("am_liam", 1.05, "octave"),
              ("af_kore", 1.05, "half190")],
    "lumi": [("af_nicole", 1.1, None), ("bf_emma", 1.0, None), ("bm_fable", 1.0, None), ("am_puck", 1.0, None),
             ("am_michael", 1.15, None), ("am_eric", 1.15, None), ("am_liam", 1.15, None), ("am_echo", 1.15, None)],
}

parser = argparse.ArgumentParser(
    description=__doc__ + " Writes one WAV per voice, and one per character with its voices in a row.",
    epilog=f"No environment variable. Needs ffmpeg, and Kokoro in {KOKORO}.\n\n"
           f"example:\n  {KOKORO}/venv/bin/python videos/voices.py --out ~/Videos/yt-publisher/voices",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", default=".", help="output directory (default: current)")
parser.add_argument("--only", choices=LINES, help="only this character")
parser.add_argument("--say", metavar="TEXT", help="say only this line, with --only and --voice, into --out/WHO-line.wav")
parser.add_argument("--voice", type=int, default=1, help="number of the voice for --say (default: 1)")
ARGS = parser.parse_args()
if ARGS.say and not ARGS.only:
    parser.error("--say needs --only")

import numpy as np  # noqa: E402  (after --help, which must work without the Kokoro environment)
from kokoro_onnx import Kokoro  # noqa: E402


def band(x, sr, lo, hi):
    s, f = np.fft.rfft(x), np.fft.rfftfreq(len(x), 1 / sr)
    s[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(s, len(x))


def monotone(x, sr, pitch=105):
    """Phase set to zero at each hop: the voice keeps its words and loses its melody."""
    hop, n = sr // pitch, 1024
    win = np.hanning(n)
    out = np.zeros(len(x) + n)
    for i in range(0, len(x) - n, hop):
        out[i:i + n] += np.fft.fftshift(np.fft.irfft(np.abs(np.fft.rfft(x[i:i + n] * win)), n)) * win
    return out[:len(x)]


def robot(x, sr, effect):
    t = np.arange(len(x)) / sr
    if effect == "monotone":
        return monotone(x, sr)
    if effect.startswith("metal"):  # a short metallic echo; metal90 = 90 % of the pitch, metal = 86 %
        x = np.interp(np.arange(0, len(x), int(effect[5:] or 86) / 100), np.arange(len(x)), x)
        d = int(.007 * sr)
        for i in range(d, len(x), d):
            part = x[i:i + d]
            part += .55 * x[i - d:i - d + len(part)]
        return x
    if effect.startswith("half"):  # half natural, half at a fixed pitch in Hz
        flat = monotone(x, sr, int(effect[4:]))
        return .5 * x / np.abs(x).max() + .6 * flat / np.abs(flat).max()
    if effect == "chorus":  # three copies, slightly late and moving
        n = np.arange(len(x))
        return x + sum(.6 * np.interp(n - sr * (d + .0015 * np.sin(2 * np.pi * f * t)), n, x)
                       for d, f in ((.009, 1.1), (.016, .7), (.023, .4)))
    if effect == "octave":  # a second voice one octave below, quieter
        n, hop = 2048, 512
        low = np.zeros(len(x) + n)
        for i in range(0, len(x) - n, hop):
            low[i:i + n] += np.interp(np.arange(n) / 2 + n / 4, np.arange(n), x[i:i + n]) * np.hanning(n)
        return x + .5 * low[:len(x)] * np.abs(x).max() / np.abs(low).max()
    if effect == "speaker":  # a light loudspeaker, without the crushing of radio
        return np.tanh(2.5 * band(x, sr, 250, 4500) / np.abs(x).max())
    if effect == "ring":
        return x * (.45 + .55 * np.sin(2 * np.pi * 60 * t))
    x = band(x, sr, 350, 2800)  # radio
    return np.round(np.tanh(6 * x / np.abs(x).max()) * 24) / 24


def save(path, x, sr):
    """16-bit WAV, at the same loudness for every voice."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((x / np.abs(x).max() * .8 * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp.name, "-af", "loudnorm=I=-16:TP=-1.5",
                        "-ar", "48000", path], check=True)


os.makedirs(ARGS.out, exist_ok=True)
kokoro = Kokoro(f"{KOKORO}/kokoro-v1.0.onnx", f"{KOKORO}/voices-v1.0.bin")
if ARGS.say:
    voice, speed, effect = VOICES[ARGS.only][ARGS.voice - 1]
    x, sr = kokoro.create(ARGS.say, voice=voice, speed=speed, lang="en-gb" if voice[0] == "b" else "en-us")
    x = np.array(x, float)
    save(os.path.join(ARGS.out, f"{ARGS.only}-line.wav"), robot(x, sr, effect) if effect else x, sr)
    sys.exit(0)
for who in [ARGS.only] if ARGS.only else LINES:
    parts = []
    for n, (voice, speed, effect) in enumerate(VOICES[who], 1):
        lines = []
        for line in LINES[who]:
            x, sr = kokoro.create(line, voice=voice, speed=speed, lang="en-gb" if voice[0] == "b" else "en-us")
            x = np.array(x, float)
            x = robot(x, sr, effect) if effect else x
            lines += [x, np.zeros(int(.35 * sr))]
        sample = np.concatenate(lines)
        path = os.path.join(ARGS.out, f"{who}-{n}-{voice[3:]}{'-' + effect if effect else ''}.wav")
        save(path, sample, sr)
        print(f"{path} ({len(sample) / sr:.1f} s)", flush=True)
        parts += [sample / np.abs(sample).max(), np.zeros(sr)]
    save(os.path.join(ARGS.out, f"all-{who}.wav"), np.concatenate(parts), sr)
sys.exit(0)
