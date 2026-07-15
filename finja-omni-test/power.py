"""
======================================================================
         Finja Omni Test – Power Monitor
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / power
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Power/Load Monitor — shows what Finja's experiment costs the battery.
  Reads the true discharge rate (Watts) via Windows-WMI + CPU load.
  Run this PARALLEL to live.py and compare with the idle value.

      python power.py            # measure every 3s
      python power.py 5          # every 5s

  (Only meaningful on battery power — on AC power, discharge is 0.)
======================================================================
"""

import sys
import time
import subprocess

import psutil

INTERVAL = int(sys.argv[1]) if len(sys.argv) > 1 else 3

_PS = ["powershell", "-NoProfile", "-Command",
       "(Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus).DischargeRate"]


def discharge_watt():
    """Current discharge rate in Watts (or None if plugged in/unreadable)."""
    try:
        out = subprocess.check_output(_PS, text=True, timeout=8).strip()
        mw = int(out)
        return mw / 1000.0 if mw > 0 else None
    except Exception:
        return None


print("=" * 56)
print("  POWER-MONITOR  (CTRL+C to exit)")
print(f"  Measuring every {INTERVAL}s  |  Watts = current battery discharge")
print("=" * 56)
print(f"  {'Watts':>6} | {'CPU%':>5} | {'Bat%':>5} | {'Avg W':>9}")
print("  " + "-" * 40)

samples = []
try:
    while True:
        cpu = psutil.cpu_percent(interval=1)        # 1s measurement window
        w = discharge_watt()
        bat = psutil.sensors_battery()
        pct = bat.percent if bat else 0
        if w:
            samples.append(w)
        avg = sum(samples) / len(samples) if samples else 0
        wtxt = f"{w:5.1f}" if w else "  AC  "
        print(f"  {wtxt:>6} | {cpu:5.1f} | {pct:5.0f} | {avg:9.1f}")
        time.sleep(max(0, INTERVAL - 1))            # -1 because of cpu_percent(1s)
except KeyboardInterrupt:
    print("  " + "-" * 40)
    if samples:
        print(f"  Average: {sum(samples)/len(samples):.1f} W  "
              f"(min {min(samples):.1f}, max {max(samples):.1f}, "
              f"{len(samples)} measurements)")
        # rough projection: how long does a typical ~50Wh battery last?
        avg = sum(samples) / len(samples)
        if avg > 0:
            print(f"  -> with ~50Wh battery approx. {50/avg:.1f}h runtime at this load")
    print()
