#!/usr/bin/env python3
"""
Project: Finja - Twitch Interactivity Suite
Module: finja-music-docker-spotify / spotify_reauth.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.1
Description: Renews the Spotify refresh token once you log in in your own browser. Since July
    2026 Spotify ends refresh tokens 6 months after the login (the app then logs FINJA-408).
New in 1.3.1: Writes hidden files (Windows refused open("w") on the hidden private/.env)
    and never loses a granted token (fallback file in the home folder).
Earlier in 1.3.0: First version. Stores the new token in private/.env (and, with
    --all-in-one-config, in the All-in-One edition's config_spotify.json); never prints it.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.

Usage (on the PC where your browser is):
    python spotify_reauth.py
    python spotify_reauth.py --all-in-one-config "<path>/config/config_spotify.json"

The redirect URI (default http://127.0.0.1:8888/callback) must be listed in your app's
settings on the Spotify developer dashboard. Spotify allows plain http only for 127.0.0.1.
"""
from __future__ import annotations

import argparse
import base64
import http.server
import json
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SCOPES = "user-read-currently-playing user-read-playback-state"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def overwrite_in_place(path: Path, text: str) -> None:
    """Rewrite an existing file without re-creating it.

    Windows refuses open(..., "w") on a file with the Hidden attribute (CREATE_ALWAYS needs the
    same attributes), and .env files are often hidden. Opening the existing file with "r+" and
    truncating keeps its attributes and permissions.
    """
    with path.open("r+", encoding="utf-8", newline="\n") as handle:
        handle.seek(0)
        handle.write(text)
        handle.truncate()


def set_env_value(path: Path, key: str, value: str) -> None:
    """Replace (or append) one KEY=value line and keep every other line as it is."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for index, line in enumerate(lines):
        if line.partition("=")[0].strip() == key:
            lines[index] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    overwrite_in_place(path, "\n".join(lines) + "\n")


def set_all_in_one_token(path: Path, refresh_token: str) -> None:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    target = config["spotify"] if isinstance(config.get("spotify"), dict) else config
    target["refresh_token"] = refresh_token
    overwrite_in_place(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def save_somewhere_private(refresh: str) -> Path:
    """Last resort when a target file cannot be written: never lose a freshly granted token."""
    fallback = Path.home() / "finja_spotify_refresh_token.txt"
    fallback.write_text(f"SPOTIFY_REFRESH_TOKEN={refresh}\n", encoding="utf-8")
    try:
        fallback.chmod(0o600)
    except OSError:
        pass  # Windows: the home folder is already private to this user
    return fallback


def exchange_code(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    data = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code,
                                   "redirect_uri": redirect_uri}).encode()
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = urllib.request.Request(TOKEN_URL, data=data, method="POST", headers={
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_code(redirect_uri: str, state: str, timeout_s: int) -> str:
    """Serve exactly one callback on the loopback redirect URI and return its ?code=."""
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname != "127.0.0.1" or not parsed.port:
        raise SystemExit("The redirect URI must look like http://127.0.0.1:<port>/<path>")
    result: dict[str, str] = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server naming)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if urllib.parse.urlparse(self.path).path != parsed.path:
                self.send_error(404)
                return
            if (query.get("state") or [""])[0] != state:
                result["error"] = "state mismatch"
            elif "error" in query:
                result["error"] = query["error"][0]
            else:
                result["code"] = (query.get("code") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            text = "Fertig, du kannst dieses Fenster schliessen." if "code" in result else "Abgebrochen."
            self.wfile.write(f"<html><body><h2>{text}</h2></body></html>".encode())

        def log_message(self, *_args):
            return

    server = http.server.HTTPServer(("127.0.0.1", parsed.port), Callback)
    server.timeout = timeout_s
    threading.Thread(target=server.handle_request, daemon=True).start()
    params = urllib.parse.urlencode({"client_id": CLIENT["id"], "response_type": "code",
                                     "redirect_uri": redirect_uri, "scope": SCOPES, "state": state,
                                     "show_dialog": "true"})
    url = f"{AUTHORIZE_URL}?{params}"
    print("Opening Spotify in your browser. If nothing opens, visit:\n" + url)
    webbrowser.open(url)
    for _ in range(timeout_s * 10):
        if result:
            break
        threading.Event().wait(0.1)
    server.server_close()
    if "code" not in result:
        raise SystemExit(f"No login received ({result.get('error', 'timeout')}).")
    return result["code"]


CLIENT: dict[str, str] = {}


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Renew the Spotify refresh token for Finja Music.")
    parser.add_argument("--env", type=Path, default=here / "private" / ".env",
                        help="env file with SPOTIFY_CLIENT_ID/SECRET; receives SPOTIFY_REFRESH_TOKEN")
    parser.add_argument("--all-in-one-config", type=Path,
                        help="also store the token in the All-in-One edition's config/config_spotify.json")
    parser.add_argument("--redirect-uri", default="http://127.0.0.1:8888/callback")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    env = read_env(args.env)
    CLIENT["id"], secret = env.get("SPOTIFY_CLIENT_ID", ""), env.get("SPOTIFY_CLIENT_SECRET", "")
    if not CLIENT["id"] or not secret:
        raise SystemExit(f"SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are needed in {args.env}")
    code = wait_for_code(args.redirect_uri, secrets.token_urlsafe(24), args.timeout)
    try:
        tokens = exchange_code(code, args.redirect_uri, CLIENT["id"], secret)
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read().decode("utf-8") or "{}")
        raise SystemExit(f"Spotify refused the code: HTTP {error.code} {detail.get('error', '')}") from None
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit("Spotify returned no refresh token.")
    failed = False
    targets = [(args.env, lambda: set_env_value(args.env, "SPOTIFY_REFRESH_TOKEN", refresh))]
    if args.all_in_one_config:
        targets.append((args.all_in_one_config, lambda: set_all_in_one_token(args.all_in_one_config, refresh)))
    for target, store in targets:
        try:
            store()
            print(f"New refresh token stored in {target}.")
        except (OSError, ValueError) as error:  # keep going: the token is single-use, so never lose it
            failed = True
            print(f"Could not write {target}: {type(error).__name__}: {error}")
    if failed:
        print(f"The token was saved to {save_somewhere_private(refresh)} instead; copy it over by hand.")
    print(f"Scope: {tokens.get('scope')}. Restart the music service so it reads the new token.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
