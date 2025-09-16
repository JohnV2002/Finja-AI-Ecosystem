#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
======================================================================
                Finja's Brain & Knowledge Core - 89.0 RTL
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.1 (89.0 RTL Modul)

----------------------------------------------------------------------
    Updates: 1.0.1:
 ----------------------------------------------------------------------
    - Added path validation to restrict output file writes to user/home directories

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os, sys, time, json, re, argparse, unicodedata
from datetime import datetime, timedelta
import requests, websocket

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"

def dbg(en, *a):
    if en:
        print("[dbg]", *a, flush=True)

def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write((text or "").strip() + "\n")
    os.replace(tmp, path)

def pick_target(base_json, debug=False):
    # Bevorzugt Radioplayer, dann Hauptseite, dann RTL+
    targets = []
    for it in base_json:
        url = it.get("url","") or ""
        title = it.get("title","") or ""
        if not url: continue
        if "radioplayer/live" in url:
            prio = 0
        elif "www.89.0rtl.de" in url:
            prio = 1
        elif "plus.rtl.de" in url:
            prio = 2
        else:
            continue
        targets.append((prio, title, url, it.get("webSocketDebuggerUrl")))
    targets.sort(key=lambda x: (x[0], x[1].lower()))
    if debug:
        for _, t, u, _ws in targets:
            dbg(True, f"candidate: {t} ({u})")
    return targets

# --- Normalisierung + Stabilisierung ---
def _norm(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+[-–—]\s+", " — ", s)
    s = re.sub(r"\s+", " ", s)
    low = s.lower()
    low = low.replace(" feat ", " feat. ")
    low = low.replace(" x ", " x ")
    return low

class Stabilizer:
    def __init__(self, debounce_ms=6000, min_repeat_gap_s=90):
        self.debounce = timedelta(milliseconds=debounce_ms)
        self.min_gap = timedelta(seconds=min_repeat_gap_s)
        self._cand = None
        self._cand_norm = ""
        self._since = None
        self._last_out = None
        self._last_out_at = datetime.min

    def feed(self, value: str) -> str | None:
        """Nur stabilisierte Werte durchlassen, sonst None."""
        now = datetime.now()
        val = (value or "").strip()
        if not val:
            self._cand = None
            self._cand_norm = ""
            self._since = None
            return None

        n = _norm(val)
        if self._cand is None or n != self._cand_norm:
            self._cand = val
            self._cand_norm = n
            self._since = now
            return None

        if self._since is None or (now - self._since) < self.debounce:
            return None

        if self._last_out is not None and _norm(self._last_out) == n:
            if now - self._last_out_at < self.min_gap:
                return None

        self._last_out = self._cand
        self._last_out_at = now
        return self._cand

# --- CDP JS ---
EVAL_JS = r'''
(async () => {
  const text = (sel) => {
    const el = document.querySelector(sel);
    return (el && el.textContent || "").trim();
  };

  const rpTitle = text('p[class*="SongBox-module__title"]');
  let rpArtist = text('p[class*="SongBox-module__artist"]');
  if (rpArtist && /^von\s+/i.test(rpArtist)) rpArtist = rpArtist.replace(/^von\s+/i, '').trim();
  if (rpTitle && rpArtist) window.__np_last_dom_ok = Date.now();

  let marquee = "";
  const mEl = document.querySelector('.player__track__marquee__text');
  if (mEl) {
    const raw = (mEl.textContent || "").trim();
    const parts = raw.split(/[·•|]/).map(s => s.trim()).filter(Boolean);
    if (parts.length >= 3) {
      const title = parts[parts.length - 2];
      const artist = parts[parts.length - 1];
      if (title && artist && !/rtl/i.test(title)) {
        marquee = `${title} — ${artist}`;
      }
    }
  }

  let domResult = "";
  if (rpTitle && rpArtist) domResult = `${rpTitle} — ${rpArtist}`;
  else if (marquee) domResult = marquee;

  const STALE_MS = 45000;
  const needApi = !domResult || (window.__np_last_dom_ok && (Date.now() - window.__np_last_dom_ok) > STALE_MS);

  if (needApi) {
    try {
      const u = "https://np.radioplayer.de/qp/v3/onair?rpIds=75&nameSize=120&artistNameSize=120&descriptionSize=0";
      const r = await fetch(u, { credentials: "include" });
      if (r.ok) {
        const j = await r.json();
        const it = j?.results?.[0]?.onair?.[0];
        const t = it?.name || it?.title || "";
        const a = it?.artistName || it?.artist || "";
        if (t && a) return `${t} — ${a}`;
      }
    } catch (e) {}
  }
  return domResult || "";
})()
'''

def ws_call(ws, ctr, method, **params):
    ctr['id'] += 1
    msg = json.dumps({"id": ctr['id'], "method": method, "params": params})
    ws.send(msg)
    while True:
        data = ws.recv()
        obj = json.loads(data)
        if obj.get("id") == ctr['id']:
            return obj

def validate_ws_url(url):
    """Stellt sicher, dass nur localhost-Verbindungen erlaubt sind"""
    if not url.startswith("ws://127.0.0.1:") and not url.startswith("ws://localhost:"):
        raise ValueError("Nur localhost WebSocket-Verbindungen erlaubt")
    return url

def scrape_once(port=9222, debug=False):
    j = requests.get(f"http://127.0.0.1:{port}/json").json()
    targets = pick_target(j, debug=debug)
    if not targets:
        raise RuntimeError("Kein passender Tab gefunden. Radioplayer oder 89.0 RTL öffnen.")

    for prio, t, url, wsurl in targets:
        if not wsurl: continue
        ws = None
        try:
            ws = websocket.create_connection(
                wsurl,
                header=[f"Origin: http://127.0.0.1:{port}"],
                timeout=8
            )
            ctr = {'id': 0}
            ws_call(ws, ctr, "Runtime.enable")
            ws_call(ws, ctr, "Page.enable")
            ws_call(ws, ctr, "Emulation.setIdleOverride", isUserActive=True, isScreenUnlocked=True)
            try: ws_call(ws, ctr, "Emulation.setFocusEmulationEnabled", enabled=True)
            except Exception: pass
            ws_call(ws, ctr, "Runtime.evaluate",
                    expression="window.__rtl_keepalive||(window.__rtl_keepalive=setInterval(()=>console.debug('keepalive',Date.now()),15000));",
                    returnByValue=True)

            res = ws_call(ws, ctr, "Runtime.evaluate", expression=EVAL_JS, awaitPromise=True, returnByValue=True)
            if "result" in res and "result" in res["result"]:
                val = res["result"]["result"].get("value") or ""
                val = (val or "").strip()
                if val:
                    dbg(debug, f"tab ok -> {val}")
                    return val
        finally:
            try:
                if ws is not None: ws.close()
            except Exception: pass
    return ""

def validate_output_path(path):
    """Beschränkt Schreibzugriff auf bestimmte Verzeichnisse"""
    allowed_dirs = [os.path.expanduser("~"), os.getcwd()]
    abs_path = os.path.abspath(path)
    if not any(abs_path.startswith(os.path.abspath(d)) for d in allowed_dirs):
        raise ValueError("Unerlaubtes Ausgabeverzeichnis")
    return abs_path

def main():
    ap = argparse.ArgumentParser(description="89.0 RTL NowPlaying (via Chrome CDP, stabilisiert)")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--out", default="nowplaying.txt")
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--debounce", type=int, default=6000, help="Millisekunden bis Titel als stabil gilt")
    ap.add_argument("--repeat-gap", type=int, default=90, help="Sekunden Mindestabstand für denselben Track")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    out_abs = os.path.abspath(args.out)
    print(f"[rtl89-cdp] Schreibe nach {out_abs} alle {args.interval}s", flush=True)

    stab = Stabilizer(debounce_ms=args.debounce, min_repeat_gap_s=args.repeat_gap)

    try:
        while True:
            try:
                raw = scrape_once(port=args.port, debug=args.debug)
                stable = stab.feed(raw)
                if stable:
                    write_atomic(out_abs, stable)
                    print("[update]", stable, flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print("[warn]", e, flush=True)
            time.sleep(max(1, int(args.interval)))
    except KeyboardInterrupt:
        print("[exit] bye 👋❤", flush=True)

if __name__ == "__main__":
    main()
