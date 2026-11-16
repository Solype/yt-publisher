#!/usr/bin/env python3
"""Upload a video to YouTube with the refresh token stored in .env."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
EPILOG = f"""environment (read from {ENV_FILE}, or from the shell):
  YT_CLIENT_ID       OAuth client ID
  YT_CLIENT_SECRET   OAuth client secret
  YT_REFRESH_TOKEN   written by yt-auth.py (needs the youtube.upload scope)

note: while the Google project is not audited, YouTube locks videos uploaded
through the API to private, whatever --privacy says.

example:
  python3 yt-upload.py demo.mp4 --title "Krc: hello world" \\
      --description-file desc.txt --tags krc,compiler --privacy unlisted
"""


def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                m = re.match(r"^export ([A-Z_]+)=(.*)$", line.strip())
                if m:
                    env[m[1]] = m[2].strip("'\"")
    env.update({k: v for k, v in os.environ.items() if k.startswith("YT_")})
    return env


def access_token(env):
    data = urllib.parse.urlencode({
        "client_id": env["YT_CLIENT_ID"],
        "client_secret": env["YT_CLIENT_SECRET"],
        "refresh_token": env["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data) as r:
        return json.load(r)["access_token"]


def main():
    p = argparse.ArgumentParser(description="Upload a video to YouTube.", epilog=EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", help="path of the video file")
    p.add_argument("--title", required=True, help="video title (max 100 characters)")
    p.add_argument("--description", default="", help="video description")
    p.add_argument("--description-file", help="read the description from this file instead")
    p.add_argument("--tags", default="", help="comma-separated tags")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private",
                   help="default: private")
    p.add_argument("--category", default="28", help="category ID, default 28 (Science & Technology)")
    a = p.parse_args()

    env = load_env()
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not env.get(k)]
    if missing:
        sys.exit(f"Missing in {ENV_FILE}: {', '.join(missing)} (run yt-auth.py first)")
    if a.description_file:
        with open(a.description_file) as f:
            a.description = f.read()
    size = os.path.getsize(a.video)

    try:
        token = access_token(env)
        meta = json.dumps({
            "snippet": {"title": a.title, "description": a.description,
                        "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
                        "categoryId": a.category},
            "status": {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False},
        }).encode()
        # Resumable upload: step 1 sends the metadata and gets the upload URL.
        req = urllib.request.Request(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            data=meta, method="POST", headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": "video/*",
            })
        with urllib.request.urlopen(req) as r:
            upload_url = r.headers["Location"]
        # Step 2 streams the file from disk, never loaded whole in memory.
        # shortcut: no resume after a network cut, re-run the upload; add chunked resume if that happens often.
        with open(a.video, "rb") as f:
            req = urllib.request.Request(upload_url, data=f, method="PUT", headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/*",
                "Content-Length": str(size),
            })
            with urllib.request.urlopen(req) as r:
                video = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"YouTube API error {e.code}: {e.read().decode()}")

    print(f"https://youtu.be/{video['id']} ({video['status']['privacyStatus']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
