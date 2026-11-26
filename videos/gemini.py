#!/usr/bin/env python3
"""Voice auditions with Gemini TTS: every character of an episode says its lines, in several voices and acted."""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from env import env

# character: (how to act, voices to try); voices and their adjectives: aistudio.google.com/docs/speech-generation
CAST = {
    "mina": ("a young developer, whiny and indignant, dragging out the long vowels, her voice rising", ["Leda", "Laomedeia", "Aoede"]),
    "stamp": ("a bored customs officer: flat, cold, final, no emotion at all", ["Alnilam", "Algenib", "Charon"]),
    "lumi": ("a mischievous guide, warm and amused, sly when making fun of someone, like a friend letting out a secret",
             ["Puck", "Sadachbia", "Zubenelgenubi"]),
}

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="environment (or a .env file in a directory above, as KEY=value or export KEY=value):\n"
           "  GEMINI_API_KEY  key of Google AI Studio\n"
           "  GEMINI_URL      another host (default: https://generativelanguage.googleapis.com)\n\n"
           "One request per voice, so 9 for the three characters. A voice already written is not asked again.\n"
           "Without billing, Google may use what is sent: only the lines of the episode are.\n\n"
           "example:\n  python3 videos/gemini.py videos/episodes/ep0.json --out ~/Videos/yt-publisher/gemini")
p.add_argument("episode", help="JSON of the episode")
p.add_argument("--out", default=".", help="directory of the WAV files, WHO-VOICE.wav (default: current)")
p.add_argument("--only", choices=CAST, help="only this character")
p.add_argument("--voices", nargs="+", metavar="NAME", help="these voices instead, with --only")
p.add_argument("--style", help="another way to act, with --only (and a new --out, to hear it again)")
p.add_argument("--model", default="gemini-3.8-flash-tts", help="model (default: gemini-3.8-flash-tts)")
A = p.parse_args()
if (A.voices or A.style) and not A.only:
    p.error("--voices and --style need --only")


def script(lines, who):
    """The lines of who in one text: cut sentences stay in one breath, separate turns are far apart."""
    text, last = "", None
    for n, line in enumerate(lines):
        if line["who"] == who:
            gap = "" if last is None else " <short pause> " if last == n - 1 else " <long pause> "
            text, last = text + gap + line["text"], n
    return text


def speak(key, text, style, voice):
    body = {"model": A.model, "response_format": {"type": "audio"},
            "input": [{"type": "user_input", "content": [
                {"type": "text", "text": text, "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "generation_config": {"speech_config": [{"voice": voice}]}}
    request = urllib.request.Request(
        env("GEMINI_URL", "https://generativelanguage.googleapis.com") + "/v1beta/interactions",
        json.dumps(body).encode(), {"x-goog-api-key": key, "Content-Type": "application/json"})
    for left in (2, 1, 0):
        try:
            with urllib.request.urlopen(request, timeout=180) as r:
                answer = json.load(r)
            break
        except urllib.error.HTTPError as e:
            error = e.read().decode(errors="replace")
            wait = re.search(r"retry in (\d+)", error)
            # the limit per minute is waited for, the limit per day is not
            if e.code != 429 or not left or not wait or int(wait[1]) > 90:
                sys.exit(f"Gemini {e.code}: {error[:600]}")
            print(f"limit reached, waiting {wait[1]} s", flush=True)
            time.sleep(int(wait[1]) + 1)
        except urllib.error.URLError as e:
            sys.exit(f"Gemini: {e.reason}")
    for step in answer.get("steps", []):
        for part in step.get("content", []) if step.get("type") == "model_output" else []:
            if part.get("type") == "audio":
                return base64.b64decode(part["data"])
    sys.exit(f"Gemini gave no sound: {json.dumps(answer)[:600]}")


key = env("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY is not set (put it in .env)")
with open(A.episode) as f:
    lines = json.load(f)["lines"]
os.makedirs(A.out, exist_ok=True)
for who in [A.only] if A.only else CAST:
    text = script(lines, who)
    if not text:
        continue
    style, names = CAST[who]
    for voice in A.voices or names:
        path = os.path.join(A.out, f"{who}-{voice}.wav")
        if not os.path.exists(path):
            sound = speak(key, text, A.style or style, voice)
            with open(path, "wb") as f:
                f.write(sound)
        print(path, flush=True)
