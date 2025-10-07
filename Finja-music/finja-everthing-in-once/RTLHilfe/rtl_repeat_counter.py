"""
======================================================================
                Finja's Brain & Knowledge Core - RTL Repeat Counter
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (RTL Modul)

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Überwacht eine `nowplaying.txt` Datei auf Änderungen.
  • Zählt die Wiederholungen jedes einzelnen Songs.
  • Speichert die Zählungen persistent in einer JSON-Datei (`repeat_counts.json`).
  • Schreibt die aktuelle Wiederholungszahl in eine `obs_repeat.txt` für die Anzeige in OBS.
  • Bereinigt die erstellten Dateien bei sauberem Beenden.

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os, json, time, argparse, signal, sys
from typing import Dict

DEFAULT_NP_PATH = r"..\Nowplaying\nowplaying.txt"
DEFAULT_OUT_DIR = r"..\Nowplaying"
DEFAULT_MEM_FILE = r"..\Memory\repeat_counts.json"

_running = True
def _sigint(_sig, _frm):
    global _running
    _running = False

def write_atomic(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write((text or "").strip() + "\n")
    os.replace(tmp, path)

def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def load_counts(mem_file: str) -> Dict[str, int]:
    try:
        with open(mem_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # defensive cast
                return {str(k): int(v) for k, v in data.items()}
    except Exception:
        pass
    return {}

def save_counts(mem_file: str, counts: Dict[str, int]) -> None:
    try:
        os.makedirs(os.path.dirname(mem_file), exist_ok=True)
    except Exception:
        pass
    tmp = mem_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)
    os.replace(tmp, mem_file)

def main():
    ap = argparse.ArgumentParser(
        description="Count repeats of nowplaying.txt and expose to obs_repeat.txt"
    )
    ap.add_argument("--np",      default=DEFAULT_NP_PATH, help="Pfad zu nowplaying.txt")
    ap.add_argument("--outdir",  default=DEFAULT_OUT_DIR, help="Outputs-Ordner (obs_* Dateien)")
    ap.add_argument("--memfile", default=DEFAULT_MEM_FILE, help="JSON mit Wiederholungszählern")
    ap.add_argument("--interval", type=int, default=2, help="Poll-Intervall in Sekunden")
    args = ap.parse_args()

    np_path   = os.path.abspath(args.np)
    out_dir   = os.path.abspath(args.outdir)
    mem_file  = os.path.abspath(args.memfile)
    interval  = max(1, int(args.interval))
    out_repeat = os.path.join(out_dir, "obs_repeat.txt")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(mem_file), exist_ok=True)

    print(f"[repeat] watching {np_path} every {interval}s", flush=True)

    signal.signal(signal.SIGINT, _sigint)
    last_seen = ""
    counts = load_counts(mem_file)

    try:
        while _running:
            cur = read_text(np_path)

            if cur and cur != last_seen:
                # nur valid pattern "title — artist" zählen (langes EM-Dash!)
                if " — " in cur:
                    counts[cur] = int(counts.get(cur, 0)) + 1
                    save_counts(mem_file, counts)
                    write_atomic(out_repeat, f"Song Wiederholung: {counts[cur]}×")
                    print(f"[repeat] {cur} -> {counts[cur]}×", flush=True)
                else:
                    # Format passt nicht -> Badge ausblenden
                    write_atomic(out_repeat, "")
                last_seen = cur

            time.sleep(interval)
    finally:
        # Aufräumen bei Exit/Ctrl+C
        try:
            if os.path.exists(mem_file):
                os.remove(mem_file)
        except Exception:
            pass
        try:
            write_atomic(out_repeat, "")
        except Exception:
            pass
        print("[repeat] bye 👋❤", flush=True)
        sys.exit(0)

if __name__ == "__main__":
    main()
