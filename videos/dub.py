#!/usr/bin/env python3
"""Dub an episode with your own voice: a local page plays it, records you in sync, and ElevenLabs changes the voice."""
import argparse
import http.server
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CHOICES = os.path.expanduser("~/.config/yt-publisher/eleven-voices.json")
NAME = re.compile(r"[\w-]{1,64}")

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="environment (or a .env file in a directory above, as KEY=value or export KEY=value):\n"
           "  ELEVENLABS_API_KEY  only needed to change the voice; a recording is sent only when you press Convert\n"
           "  ELEVENLABS_URL      another host (default: https://api.elevenlabs.io)\n\n"
           "Needs ffmpeg, and the episode already made once by episode.py. The takes go in OUT/EPISODE-dub, where\n"
           f"episode.py finds them. The voice of each character is kept in {CHOICES}\n\n"
           "example:\n  python3 videos/dub.py videos/episodes/ep0.json --out ~/Videos/yt-publisher\n"
           "  python3 videos/episode.py videos/episodes/ep0.json --out ~/Videos/yt-publisher")
p.add_argument("episode", help="JSON of the episode")
p.add_argument("--out", default=".", help="directory of the MP4, as for episode.py (default: current)")
p.add_argument("--port", type=int, default=8737, help="port on this machine (default: 8737)")
A = p.parse_args()

name = os.path.splitext(os.path.basename(A.episode))[0]
VIDEO = os.path.join(A.out, f"{name}.mp4")
TIMELINE = os.path.expanduser(f"~/.cache/yt-publisher/{name}/timeline.json")
SOUND = os.path.join(os.path.dirname(TIMELINE), "mix.wav")
DUB = os.path.join(A.out, f"{name}-dub")


def env(key, default=None):
    """The variable, else the one of the nearest .env above this file that has it."""
    if os.environ.get(key):
        return os.environ[key]
    d = HERE
    while d != os.path.dirname(d):
        d = os.path.dirname(d)
        if os.path.exists(f"{d}/.env"):
            with open(f"{d}/.env") as f:
                for line in f:
                    m = re.match(rf"(?:export )?{key}=(.*)$", line.strip())
                    if m:
                        return m[1].strip("'\"")
    return default


def eleven(path, data=None, kind=None):
    key = env("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set (put it in .env)")
    headers = {"xi-api-key": key} | ({"Content-Type": kind} if kind else {})
    request = urllib.request.Request(env("ELEVENLABS_URL", "https://api.elevenlabs.io") + path, data, headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs {e.code}: {e.read().decode(errors='replace')[:400]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"ElevenLabs: {e.reason}") from None


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(value, f)


def ffmpeg(data, out):
    """Any recording, to the WAV that mix.py reads; first_pts keeps a late first packet late."""
    done = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", "pipe:0", "-vn", "-af", "aresample=async=1:first_pts=0",
                           "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", "-bitexact", "-f", "wav", out + ".part"],
                          input=data, capture_output=True)
    if done.returncode:
        raise RuntimeError("ffmpeg: " + done.stderr.decode(errors="replace")[-300:])
    os.replace(out + ".part", out)


def take(n, end):
    return os.path.join(DUB, f"{n:02}{end}")


def remove(*paths):
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


def change_voice(wav, voice):
    edge = uuid.uuid4().hex
    body = b"".join(f'--{edge}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in (("model_id", "eleven_multilingual_sts_v2"),))
    body += (f'--{edge}\r\nContent-Disposition: form-data; name="audio"; filename="take.wav"\r\n'
             "Content-Type: audio/wav\r\n\r\n").encode() + wav + f"\r\n--{edge}--\r\n".encode()
    return eleven(f"/v1/voice-changer/{voice}?output_format=mp3_44100_128", body, f"multipart/form-data; boundary={edge}")


def state():
    with open(TIMELINE) as f:
        lines = json.load(f)["lines"]
    for n, line in enumerate(lines):
        line["take"] = load(take(n, ".json"), None)
        line["done"] = os.path.exists(take(n, ".wav"))
    return {"name": name, "lines": lines, "choices": load(CHOICES, {}), "key": bool(env("ELEVENLABS_API_KEY")),
            "command": f"python3 videos/episode.py {A.episode} --out {A.out}"}


def all_voices():
    found, token = [], ""
    while True:
        page = json.loads(eleven("/v2/voices?page_size=100" + (f"&next_page_token={urllib.parse.quote(token)}" if token else "")))
        found += [{k: v.get(k) for k in ("voice_id", "name", "preview_url", "labels")} for v in page["voices"]]
        token = page.get("next_page_token")
        if not page.get("has_more") or not token:
            return found


class Page(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, kind="application/json", code=200, **headers):
        body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        for k, v in {"Content-Type": kind, "Content-Length": len(body), "Cache-Control": "no-store", **headers}.items():
            self.send_header(k.replace("_", "-"), str(v))
        self.end_headers()
        self.wfile.write(body)

    def file(self, path, kind):
        with open(path, "rb") as f:
            data = f.read()
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if not m:
            return self.reply(data, kind, Accept_Ranges="bytes")
        a, b = int(m[1]), min(int(m[2] or len(data) - 1), len(data) - 1)
        self.reply(data[a:b + 1], kind, 206, Accept_Ranges="bytes", Content_Range=f"bytes {a}-{b}/{len(data)}")

    def handle_one(self, post):
        # Only this page may talk to the server: another site cannot set X-Dub, nor have this Host.
        if self.headers.get("Host") not in (f"localhost:{A.port}", f"127.0.0.1:{A.port}") or (post and not self.headers.get("X-Dub")):
            return self.reply({"error": "refused"}, code=403)
        url = urllib.parse.urlsplit(self.path)
        ask = dict(urllib.parse.parse_qsl(url.query))
        what, _, n = url.path.strip("/").partition("/")
        try:
            n = int(n) if n else None
            if n is not None and not 0 <= n < len(state()["lines"]):
                raise ValueError("no such line")
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if post else b""
            answer = self.post(what, n, ask, body) if post else self.get(what, n, ask)
            if answer is not None:
                self.reply(answer)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser stops reading a video when it seeks
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            self.reply({"error": str(e)}, code=400)

    def do_GET(self):
        self.handle_one(False)

    def do_POST(self):
        self.handle_one(True)

    def get(self, what, n, ask):
        if what == "":
            return self.file(f"{HERE}/dub.html", "text/html; charset=utf-8")
        if what == "video":
            return self.file(VIDEO, "video/mp4")
        if what == "sound":
            return self.file(SOUND, "audio/wav")
        if what == "take" and n is not None:
            return self.file(take(n, ".wav" if ask.get("done") else ".raw.wav"), "audio/wav")
        if what == "state":
            return state()
        if what == "voices":
            return all_voices()
        raise ValueError("unknown path")

    def post(self, what, n, ask, body):
        if what == "choices":
            choices = json.loads(body)
            if not all(isinstance(v, str) and NAME.fullmatch(v) for v in choices.values()):
                raise ValueError("bad voice")
            save(CHOICES, choices)
        elif n is None:
            raise ValueError("no line")
        elif what == "take":
            os.makedirs(DUB, exist_ok=True)
            at = float(ask["at"])
            ffmpeg(body, take(n, ".raw.wav"))
            remove(take(n, ".wav"))
            save(take(n, ".json"), {"at": at})
        elif what == "at":
            save(take(n, ".json"), {"at": float(ask["at"])})
        elif what == "convert":
            with open(take(n, ".raw.wav"), "rb") as f:
                wav = f.read()
            voice = ask["voice"]
            if not NAME.fullmatch(voice):
                raise ValueError("bad voice")
            ffmpeg(wav if voice == "own" else change_voice(wav, voice), take(n, ".wav"))
        elif what == "drop":
            remove(*(take(n, end) for end in (".raw.wav", ".wav", ".json")))
        else:
            raise ValueError("unknown path")
        return {"ok": True}


for path in (VIDEO, TIMELINE, SOUND):
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: make the episode once with episode.py")
print(f"http://localhost:{A.port}  (Ctrl C to stop)", flush=True)
try:
    http.server.ThreadingHTTPServer(("127.0.0.1", A.port), Page).serve_forever()
except KeyboardInterrupt:
    pass
