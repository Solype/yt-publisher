#!/usr/bin/env python3
"""Get a YouTube OAuth refresh token and save it as YT_REFRESH_TOKEN in the env file."""
import http.server
import json
import os
import re
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
HELP = f"""Usage: yt-auth.py [--scope SCOPE ...] [-h|--help]

Opens Google's consent page, catches the authorization code on a local
loopback port, exchanges it for a refresh token and writes
YT_REFRESH_TOKEN into {ENV_FILE} (replaced if already there).
The token is never printed.

Options:
  --scope SCOPE   OAuth scope suffix after https://www.googleapis.com/auth/
                  Repeatable. Default: youtube.upload
                  Others: youtube (full), youtube.force-ssl (edit, comments),
                  youtube.readonly, yt-analytics.readonly
  -h, --help      Show this help and exit.

Environment (read from {ENV_FILE}, or from the shell):
  YT_CLIENT_ID      OAuth client ID (Desktop app type)
  YT_CLIENT_SECRET  OAuth client secret

Example:
  python3 yt-auth.py --scope youtube.upload --scope youtube.force-ssl
"""


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            m = re.match(r"^export ([A-Z_]+)=(.*)$", line.strip())
            if m:
                env[m[1]] = m[2].strip("'\"")
    return env


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(HELP)
        return 0
    scopes = [args[i + 1] for i, a in enumerate(args) if a == "--scope" and i + 1 < len(args)]
    scopes = scopes or ["youtube.upload"]

    env = load_env()
    client_id = os.environ.get("YT_CLIENT_ID") or env.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET") or env.get("YT_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(f"YT_CLIENT_ID / YT_CLIENT_SECRET missing in {ENV_FILE}")

    state = secrets.token_urlsafe(16)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [None])[0] != state:
                result["error"] = "state mismatch"
            else:
                result["code"] = q.get("code", [None])[0]
                result["error"] = q.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("OK, tu peux fermer cet onglet.".encode())

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join("https://www.googleapis.com/auth/" + s for s in scopes),
        "access_type": "offline",
        "prompt": "consent",  # forces a refresh token even if already granted
        "state": state,
    })
    print("Ouvre cette URL si le navigateur ne s'ouvre pas :\n" + url, flush=True)
    webbrowser.open(url)
    while "code" not in result and "error" not in result:
        server.handle_request()
    if not result.get("code"):
        sys.exit(f"Autorisation refusée : {result.get('error')}")

    data = urllib.parse.urlencode({
        "code": result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }).encode()
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", data) as r:
            token = json.load(r).get("refresh_token")
    except urllib.error.HTTPError as e:
        sys.exit(f"Échange du code refusé : {e.code} {e.read().decode()}")
    if not token:
        sys.exit("Pas de refresh_token dans la réponse.")

    with open(ENV_FILE) as f:
        lines = [l for l in f if not l.startswith("export YT_REFRESH_TOKEN=")]
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append(f"export YT_REFRESH_TOKEN={token}\n")
    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.writelines(lines)
    print(f"YT_REFRESH_TOKEN enregistré dans {ENV_FILE} (scopes : {', '.join(scopes)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
