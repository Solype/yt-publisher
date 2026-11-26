#!/usr/bin/env python3
"""Cut a take into its lines, in the silences between them, found by listening to the words."""
import argparse
import difflib
import os
import re
import subprocess
import sys
import wave

HOME = os.path.expanduser("~/.local/share/chatterbox")
p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=f"No environment variable. Needs ffmpeg, and faster-whisper in {HOME}.\n\n"
           f"example:\n  {HOME}/venv/bin/python videos/cut.py lumi.wav --lines 'He is just...' 'dumb.' --out a.wav b.wav")
p.add_argument("take", help="WAV, 16-bit mono")
p.add_argument("--lines", nargs="+", required=True, help="what is said, line by line")
p.add_argument("--out", nargs="+", required=True, help="one 48 kHz WAV per line")
A = p.parse_args()
if len(A.lines) != len(A.out):
    p.error("as many --out as --lines")

os.environ["HF_HOME"] = HOME + "/hf"
import numpy as np  # noqa: E402  (after --help, which must work without the environment)
from faster_whisper import WhisperModel  # noqa: E402

with wave.open(A.take) as w:
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


SOUNDS = {"too": "two", "to": "two"}  # words that sound the same


def plain(text):
    return [SOUNDS.get(w, w) for w in re.sub(r"<.*?>|[^a-z0-9 ]", "", text.lower()).split()]


def silences():
    """The (start, end) of every silence of 80 ms or more inside the take."""
    hop = sr // 100
    on = np.flatnonzero([np.abs(x[i:i + hop]).max() > .04 for i in range(0, len(x), hop)])
    return [((a + 1) / 100, b / 100) for a, b in zip(on, on[1:]) if b - a > 8]


marks = [0.0]
if len(A.lines) > 1:
    y = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
    parts, _ = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4).transcribe(
        y, language="en", word_timestamps=True, condition_on_previous_text=False)
    heard = [(p, w) for s in parts for w in s.words for p in plain(w.word)]
    wanted = [plain(line) for line in A.lines]
    flat = [word for line in wanted for word in line]
    same = {}
    for i, j, n in difflib.SequenceMatcher(None, flat, [h[0] for h in heard], False).get_matching_blocks():
        same.update((i + k, j + k) for k in range(n))
    first = 0
    for line in wanted[:-1]:
        first += len(line)
        if first in same and same[first]:  # the word that opens the next line, else the one that closes this one
            j = same[first]
        elif first - 1 in same and same[first - 1] + 1 < len(heard):
            j = same[first - 1] + 1
        elif (before := max((i for i in same if i < first), default=None)) is not None and \
                (after := min((i for i in same if i >= first), default=None)) is not None and same[after] - same[before] > 1:
            # misheard words on both sides: share the heard words between the wanted ones, in proportion
            j = same[before] + 1 + round((first - before - 1) * (same[after] - same[before] - 1) / (after - before - 1))
            j = min(max(j, same[before] + 1), same[after])
        else:
            sys.exit(f"cannot cut before {flat[first]!r}: heard {' '.join(h[0] for h in heard)}")
        near = (heard[j - 1][1].end + heard[j][1].start) / 2
        # the longest one around: the closest can be inside the last word, before its final t; and whisper can place
        # a short last word half a second early, inside the word before it
        around = [s for s in silences() if max(s[0] - near, near - s[1]) <= .6]
        a, b = max(around, key=lambda s: s[1] - s[0], default=(0, 0))
        if not b or (a + b) / 2 <= marks[-1]:
            sys.exit(f"no silence near {near:.2f} s, before {flat[first]!r}")
        marks.append((a + b) / 2)
marks.append(len(x) / sr)
for path, a, b in zip(A.out, marks, marks[1:]):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(a), "-to", str(b), "-i", A.take, "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s16le", path], check=True)
    print(f"{path}: {a:.2f}-{b:.2f} s")
