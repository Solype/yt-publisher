#!/usr/bin/env python3
"""Mina's lines played by Chatterbox (local): several tries per line, the garbled ones thrown away."""
import argparse
import difflib
import os
import re
import subprocess
import sys
import time
import wave

HOME = os.path.expanduser("~/.local/share/chatterbox")
# (text, pause after in s); whole sentences only: Chatterbox garbles pieces of one or two words
LINES = [("But I gave it a number!", .7), ("Refused? What do you mean, refused?!", .8), ("Okay, okay! How about now?", .5)]

parser = argparse.ArgumentParser(
    description=__doc__,
    epilog="Environment: HF_HOME is set to " + HOME + "/hf. Needs ffmpeg. Run it under a memory cap.\n\nexample:\n"
           "  systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0 \\\n"
           f"    {HOME}/venv/bin/python videos/acting.py --ref bella.wav --out takes",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--ref", action="append", required=True,
                    help="WAV of the voice to imitate, 6 to 10 s, or builtin for the voice of Chatterbox; repeatable")
parser.add_argument("--out", default=".", help="output directory (default: current)")
parser.add_argument("--tries", type=int, default=3, help="tries per line (default: 3)")
parser.add_argument("--exaggeration", type=float, default=.7, help="0.5 is neutral (default: 0.7)")
parser.add_argument("--say", help="play only this text, instead of the audition lines")
parser.add_argument("--cut", type=int, nargs="+", metavar="WORDS",
                    help="with --say: also write it in pieces of that many words, VOICE-acted-0.wav and so on")
ARGS = parser.parse_args()

os.environ["HF_HOME"] = HOME + "/hf"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
import librosa  # noqa: E402  (after --help, which must work without the environment)
import numpy as np  # noqa: E402
import torch  # noqa: E402
from chatterbox.tts import ChatterboxTTS  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

torch.set_num_threads(6)  # other sessions share the machine
model = ChatterboxTTS.from_pretrained(device="cpu")
ears = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=6)
builtin = model.conds


def words(s):
    return re.findall(r"[a-z']+", re.sub(r"(.)\1+", r"\1", s.lower()).replace("ok ", "okay ").replace("ok.", "okay").replace("ok,", "okay"))


def review(x, text):
    """How much of the text is heard back (0 to 1), and how wide the melody is (p90 / p10 of the pitch)."""
    heard, _ = ears.transcribe(librosa.resample(x, orig_sr=model.sr, target_sr=16000), beam_size=5,
                               condition_on_previous_text=False)
    heard = " ".join(s.text.strip() for s in heard)
    f0, voiced, _ = librosa.pyin(x, fmin=80, fmax=600, sr=model.sr)
    f0 = f0[voiced]
    wide = np.percentile(f0, 90) / np.percentile(f0, 10) if len(f0) > 5 else 0
    return difflib.SequenceMatcher(None, words(heard), words(text)).ratio(), wide, heard


os.makedirs(ARGS.out, exist_ok=True)
for ref in ARGS.ref:
    voice, start, parts = os.path.splitext(os.path.basename(ref))[0], time.time(), []
    for text, pause in [(ARGS.say, 0)] if ARGS.say else LINES:
        best = None
        for n in range(ARGS.tries):
            torch.manual_seed(11 + n)
            if ref == "builtin":
                model.conds = builtin
            else:
                model.prepare_conditionals(ref, exaggeration=ARGS.exaggeration)
            x = model.generate(text, exaggeration=ARGS.exaggeration, cfg_weight=.4).squeeze(0).numpy()
            loud = np.flatnonzero(np.abs(x) > .02 * np.abs(x).max())
            x = x[max(0, loud[0] - model.sr // 50):loud[-1] + model.sr // 20]
            fade = np.minimum(1, np.minimum(np.arange(len(x)), np.arange(len(x))[::-1]) / (.01 * model.sr))
            x = (x * fade).astype(np.float32)
            match, wide, heard = review(x, text)
            print(f"  {voice}, try {n + 1}: match {match:.2f}, melody x{wide:.2f}, heard: {heard}", flush=True)
            # the right words first, then the widest melody
            if best is None or (match >= .95, match if match < .95 else wide) > best[0]:
                best = (match >= .95, match if match < .95 else wide), x
        if not best[0][0]:
            print(f"  {voice}: no clean try of '{text}'", flush=True)
        parts += [best[1] / np.abs(best[1]).max() * .6, np.zeros(int(pause * model.sr))]
    sound = np.concatenate(parts)
    pieces = [("", sound)]
    if ARGS.cut:
        heard, _ = ears.transcribe(librosa.resample(sound.astype(np.float32), orig_sr=model.sr, target_sr=16000),
                                   word_timestamps=True, condition_on_previous_text=False)
        heard = [w for s in heard for w in s.words]
        assert len(heard) == sum(ARGS.cut), f"cannot cut {[w.word for w in heard]} into {ARGS.cut} words"
        ends = np.cumsum(ARGS.cut)[:-1]
        marks = [0] + [int((heard[k - 1].end + heard[k].start) / 2 * model.sr) for k in ends] + [len(sound)]
        pieces += [(f"-{k}", sound[a:b]) for k, (a, b) in enumerate(zip(marks, marks[1:]))]
    for suffix, sound in pieces:
        path, raw = os.path.join(ARGS.out, f"{voice}-acted{suffix}.wav"), os.path.join(ARGS.out, "raw.wav")
        with wave.open(raw, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(model.sr)
            w.writeframes((sound * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-af", "loudnorm=I=-16:TP=-1.5", "-ar", "48000",
                        path], check=True)
        os.remove(raw)
        print(f"{path}: {len(sound) / model.sr:.1f} s of sound in {time.time() - start:.0f} s", flush=True)
sys.exit(0)
