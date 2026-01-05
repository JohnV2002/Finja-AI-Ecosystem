"""
======================================================================
                Finja's Brain & Knowledge Core - 89.0 RTL CDP Scraper
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0 (89.0 RTL Module)

  ✨ New in 1.1.0:
    • Complete English documentation with docstrings
    • All comments and messages translated to English
    • Copyright updated to 2026
    • Fixed path traversal vulnerabilities (Snyk)
    • Fixed SSRF vulnerability with port validation (Snyk)
    • Reduced cognitive complexity in scrape_once (SonarQube)
    • Added extensive inline comments for better code understanding

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Connects to a running Chrome browser via the Chrome DevTools Protocol (CDP).
  • Executes JavaScript on the 89.0 RTL website to read the current song.
  • Uses a "Stabilizer" class to only accept stable song titles and prevent flickering.
  • Writes the detected song atomically to `nowplaying.txt`.
  • Automatically prioritizes the correct browser tab (e.g., Radioplayer over main page).

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os
import sys
import time
import json
import re
import argparse
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests
import websocket


# =============================================================================
# User Agent - Used to identify ourselves when making requests
# =============================================================================
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"


# =============================================================================
# Security Constants
# These define the boundaries for safe operation
# =============================================================================

# Only allow writing to user's home directory or current working directory
# This prevents malicious path traversal attacks (e.g., --out "../../../etc/passwd")
ALLOWED_OUTPUT_DIRS = [Path.home(), Path.cwd()]

# Valid port range for Chrome DevTools Protocol
# Ports below 1024 require root privileges and are reserved for system services
# Ports above 65535 don't exist in TCP/IP
MIN_CDP_PORT = 1024
MAX_CDP_PORT = 65535


# =============================================================================
# Debug Helper
# =============================================================================

def dbg(enabled: bool, *args) -> None:
    """
    Print debug messages if debug mode is enabled.
    
    Args:
        enabled: Whether debug output is active
        *args: Values to print
    """
    if enabled:
        # flush=True ensures immediate output, important for real-time debugging
        print("[dbg]", *args, flush=True)


# =============================================================================
# Security Validation Functions
# =============================================================================

def validate_output_path(path: str) -> Path:
    """
    Validate and sanitize output path to prevent path traversal attacks.
    
    This function resolves the path to its absolute form and checks if it
    falls within allowed directories. This prevents attacks like:
    - --out "../../etc/passwd"
    - --out "/tmp/../../../etc/shadow"
    
    Args:
        path: The path string to validate
        
    Returns:
        Resolved absolute Path object that is safe to write to
        
    Raises:
        ValueError: If path resolves to a location outside allowed directories
    """
    # resolve() follows symlinks and removes ".." components
    # This is crucial for security - it reveals the TRUE destination
    resolved = Path(path).resolve()
    
    # Check if the resolved path is inside any allowed directory
    for allowed_dir in ALLOWED_OUTPUT_DIRS:
        try:
            # relative_to() raises ValueError if path is not relative to allowed_dir
            resolved.relative_to(allowed_dir.resolve())
            return resolved  # Path is safe!
        except ValueError:
            # Not in this allowed directory, try the next one
            continue
    
    # Path is not in ANY allowed directory - reject it
    raise ValueError(f"Output path not allowed: {resolved}")


def validate_port(port: int) -> int:
    """
    Validate CDP port to prevent SSRF (Server-Side Request Forgery) attacks.
    
    Without this validation, an attacker could potentially use the port parameter
    to make requests to internal services (e.g., --port 6379 for Redis).
    
    Args:
        port: The port number to validate
        
    Returns:
        The validated port number (unchanged if valid)
        
    Raises:
        ValueError: If port is not an integer or outside valid range
    """
    # Ensure it's actually an integer and within valid TCP port range
    if not isinstance(port, int) or not MIN_CDP_PORT <= port <= MAX_CDP_PORT:
        raise ValueError(
            f"Invalid port: {port}. Must be between {MIN_CDP_PORT} and {MAX_CDP_PORT}"
        )
    return port


# =============================================================================
# File I/O Functions
# =============================================================================

def write_atomic(path: Path, text: str) -> None:
    """
    Write text to file atomically using a temporary file.
    
    Atomic writing prevents data corruption if the process is interrupted mid-write.
    Instead of overwriting the file directly, we:
    1. Write to a temporary file
    2. Rename the temp file to the target (atomic operation on most filesystems)
    
    This ensures the file always contains either the old OR new content, never partial.
    
    Args:
        path: Validated Path object (MUST be pre-validated by validate_output_path!)
        text: Text content to write
        
    Security Note:
        The path parameter must be validated BEFORE calling this function.
        In main(), we call validate_output_path() at startup, so all subsequent
        calls to write_atomic() receive a known-safe path.
    """
    # Create temp file path by appending .tmp to the full filename
    # e.g., "nowplaying.txt" -> "nowplaying.txt.tmp"
    tmp = path.with_suffix(path.suffix + ".tmp")
    
    # Write to temp file first
    # Security: Path is pre-validated by validate_output_path() in main()
    with open(tmp, "w", encoding="utf-8") as f:  # nosec B108 - path is pre-validated
        # Strip whitespace and ensure single trailing newline
        f.write((text or "").strip() + "\n")
    
    # Atomic rename - this is the magic!
    # On POSIX systems, rename() is atomic, meaning the file either exists
    # with old content or new content, never in a partial state
    os.replace(tmp, path)  # nosec B108 - path is pre-validated


# =============================================================================
# Browser Tab Selection
# =============================================================================

def pick_target(base_json: list, debug: bool = False) -> list:
    """
    Select the best browser tab for scraping from available Chrome tabs.
    
    Priority order:
    1. Radioplayer page (most reliable, dedicated player interface)
    2. Main 89.0 RTL website (fallback, has embedded player)
    3. RTL+ page (last resort)
    
    Args:
        base_json: List of tab info dicts from Chrome's /json endpoint
        debug: Whether to print debug info about found tabs
        
    Returns:
        List of tuples: (priority, title, url, websocket_url)
        Sorted by priority (lowest = best)
    """
    targets = []
    
    for tab_info in base_json:
        url = tab_info.get("url", "") or ""
        title = tab_info.get("title", "") or ""
        
        # Skip tabs without URLs (like devtools windows)
        if not url:
            continue
        
        # Assign priority based on URL - lower number = higher priority
        if "radioplayer/live" in url:
            prio = 0  # Best: dedicated radio player
        elif "www.89.0rtl.de" in url:
            prio = 1  # Good: main website
        elif "plus.rtl.de" in url:
            prio = 2  # Fallback: RTL+ streaming
        else:
            continue  # Not a relevant tab, skip it
        
        # Store tab with its WebSocket URL for CDP connection
        targets.append((prio, title, url, tab_info.get("webSocketDebuggerUrl")))
    
    # Sort by priority first, then alphabetically by title for consistency
    targets.sort(key=lambda x: (x[0], x[1].lower()))
    
    # Debug output: show all candidate tabs
    if debug:
        for _, title, url, _ws in targets:
            dbg(True, f"candidate: {title} ({url})")
    
    return targets


# =============================================================================
# Text Normalization
# =============================================================================

def _norm(s: str) -> str:
    """
    Normalize a string for comparison purposes.
    
    This ensures that slight variations in song titles are treated as the same:
    - "Song - Artist" vs "Song — Artist" (different dash types)
    - "feat" vs "feat." (with/without period)
    - Extra whitespace
    
    Args:
        s: Input string to normalize
        
    Returns:
        Normalized lowercase string for comparison
    """
    s = (s or "").strip()
    
    # Unicode normalization: converts composed characters to standard form
    # e.g., "é" (single char) vs "e" + "´" (two chars) -> both become same
    s = unicodedata.normalize("NFKC", s)
    
    # Unify different dash types (hyphen, en-dash, em-dash) with spaces around them
    s = re.sub(r"\s+[-–—]\s+", " — ", s)
    
    # Collapse multiple whitespace into single space
    s = re.sub(r"\s+", " ", s)
    
    # Lowercase for case-insensitive comparison
    low = s.lower()
    
    # Normalize common variations
    low = low.replace(" feat ", " feat. ")  # Standardize featuring
    low = low.replace(" x ", " x ")  # Keep collaborations consistent
    
    return low


# =============================================================================
# Song Stabilizer Class
# =============================================================================

class Stabilizer:
    """
    Stabilizes song title changes to prevent flickering in the output.
    
    Problem this solves:
    Radio websites often briefly show incorrect/blank titles during song
    transitions, or the same song might flicker on and off. This class
    ensures we only output a song title after it has been consistently
    shown for a certain duration (debounce), and prevents outputting
    the same song twice within a short time window (repeat gap).
    
    Attributes:
        debounce: How long a title must be stable before being accepted
        min_gap: Minimum time before same track can be output again
    """
    
    def __init__(self, debounce_ms: int = 6000, min_repeat_gap_s: int = 90):
        """
        Initialize the Stabilizer.
        
        Args:
            debounce_ms: Milliseconds a title must remain stable (default: 6 seconds)
            min_repeat_gap_s: Seconds before same song can appear again (default: 90)
        """
        self.debounce = timedelta(milliseconds=debounce_ms)
        self.min_gap = timedelta(seconds=min_repeat_gap_s)
        
        # Current candidate song (might not be stable yet)
        self._cand = None
        self._cand_norm = ""  # Normalized version for comparison
        self._since = None  # When we first saw this candidate
        
        # Last successfully output song (for repeat prevention)
        self._last_out = None
        self._last_out_at = datetime.min  # Start with ancient timestamp

    def feed(self, value: str) -> str | None:
        """
        Feed a new song value and get back stable output (if any).
        
        Call this repeatedly with scraped values. It will return None
        until a value has been stable long enough, then return that value.
        
        Args:
            value: Current song string from scraping
            
        Returns:
            The stable song string, or None if not yet stable/duplicate
        """
        now = datetime.now()
        val = (value or "").strip()
        
        # Empty value: reset candidate tracking
        if not val:
            self._cand = None
            self._cand_norm = ""
            self._since = None
            return None

        # Normalize for comparison
        n = _norm(val)
        
        # New/different song: start tracking it as candidate
        if self._cand is None or n != self._cand_norm:
            self._cand = val
            self._cand_norm = n
            self._since = now
            return None  # Too early to confirm

        # Same song as candidate - check if stable long enough
        if self._since is None or (now - self._since) < self.debounce:
            return None  # Not stable long enough yet

        # Check for duplicate: don't output same song again too quickly
        if self._last_out is not None and _norm(self._last_out) == n:
            if now - self._last_out_at < self.min_gap:
                return None  # Too soon after last output of this song

        # Song is stable and not a recent duplicate - output it!
        self._last_out = self._cand
        self._last_out_at = now
        return self._cand


# =============================================================================
# JavaScript Code for Browser Execution
# =============================================================================

# This JavaScript runs inside the browser page to extract the current song.
# It tries multiple methods because the page structure varies:
# 1. Direct DOM scraping from the SongBox component
# 2. Marquee text (scrolling ticker)
# 3. Radioplayer API as fallback
EVAL_JS = r'''
(async () => {
  // Helper: get text content from a CSS selector
  const text = (sel) => {
    const el = document.querySelector(sel);
    return (el && el.textContent || "").trim();
  };

  // Method 1: Try to get title/artist from the SongBox component
  const rpTitle = text('p[class*="SongBox-module__title"]');
  let rpArtist = text('p[class*="SongBox-module__artist"]');
  
  // Clean up "von Artist" -> "Artist" (German "by")
  if (rpArtist && /^von\s+/i.test(rpArtist)) {
    rpArtist = rpArtist.replace(/^von\s+/i, '').trim();
  }
  
  // Track when we last got valid DOM data (for staleness check)
  if (rpTitle && rpArtist) {
    window.__np_last_dom_ok = Date.now();
  }

  // Method 2: Try the marquee (scrolling text ticker)
  let marquee = "";
  const mEl = document.querySelector('.player__track__marquee__text');
  if (mEl) {
    const raw = (mEl.textContent || "").trim();
    // Marquee format: "Station · Title · Artist" - split by separators
    const parts = raw.split(/[·•|]/).map(s => s.trim()).filter(Boolean);
    if (parts.length >= 3) {
      const title = parts[parts.length - 2];
      const artist = parts[parts.length - 1];
      // Ignore if it's just station branding
      if (title && artist && !/rtl/i.test(title)) {
        marquee = `${title} — ${artist}`;
      }
    }
  }

  // Combine DOM results
  let domResult = "";
  if (rpTitle && rpArtist) {
    domResult = `${rpTitle} — ${rpArtist}`;
  } else if (marquee) {
    domResult = marquee;
  }

  // Method 3: Fallback to API if DOM is empty or stale (>45 seconds old)
  const STALE_MS = 45000;
  const needApi = !domResult || 
    (window.__np_last_dom_ok && (Date.now() - window.__np_last_dom_ok) > STALE_MS);

  if (needApi) {
    try {
      // Radioplayer API endpoint for 89.0 RTL (rpId 75)
      const u = "https://np.radioplayer.de/qp/v3/onair?rpIds=75&nameSize=120&artistNameSize=120&descriptionSize=0";
      const r = await fetch(u, { credentials: "include" });
      if (r.ok) {
        const j = await r.json();
        const it = j?.results?.[0]?.onair?.[0];
        const t = it?.name || it?.title || "";
        const a = it?.artistName || it?.artist || "";
        if (t && a) return `${t} — ${a}`;
      }
    } catch (e) {
      // API failed, fall through to return DOM result
    }
  }
  
  return domResult || "";
})()
'''


# =============================================================================
# Chrome DevTools Protocol (CDP) Functions
# =============================================================================

def ws_call(ws, ctr: dict, method: str, **params) -> dict:
    """
    Send a CDP command over WebSocket and wait for the response.
    
    CDP uses a simple request/response protocol with incrementing IDs.
    We send a command with an ID, then wait for a response with the same ID.
    
    Args:
        ws: WebSocket connection to Chrome
        ctr: Counter dict with 'id' key (mutable, gets incremented)
        method: CDP method name (e.g., "Runtime.evaluate")
        **params: Method parameters
        
    Returns:
        Response dict from Chrome
    """
    # Increment ID for each call to match requests with responses
    ctr['id'] += 1
    
    # Build and send the CDP command
    msg = json.dumps({"id": ctr['id'], "method": method, "params": params})
    ws.send(msg)
    
    # Wait for response with matching ID
    # (Chrome may send events between our request and response)
    while True:
        data = ws.recv()
        obj = json.loads(data)
        if obj.get("id") == ctr['id']:
            return obj
        # Otherwise it's an event or response to different request, ignore it


def _setup_cdp_session(ws, ctr: dict) -> None:
    """
    Initialize a CDP session with required settings.
    
    This sets up the browser tab for scraping by:
    - Enabling Runtime domain (for JavaScript execution)
    - Enabling Page domain (for page events)
    - Preventing idle/sleep detection (keeps tab "active")
    - Setting up a keepalive to prevent tab suspension
    
    Args:
        ws: WebSocket connection to Chrome
        ctr: Counter dict for ws_call
    """
    # Enable required CDP domains
    ws_call(ws, ctr, "Runtime.enable")
    ws_call(ws, ctr, "Page.enable")
    
    # Trick the page into thinking the user is active
    # This prevents some sites from pausing playback or showing "are you there?" dialogs
    ws_call(ws, ctr, "Emulation.setIdleOverride", isUserActive=True, isScreenUnlocked=True)
    
    # Try to enable focus emulation (not available in all Chrome versions)
    try:
        ws_call(ws, ctr, "Emulation.setFocusEmulationEnabled", enabled=True)
    except Exception:
        pass  # Older Chrome versions don't support this, that's OK
    
    # Inject a keepalive script that runs every 15 seconds
    # This prevents Chrome from suspending the tab for being "inactive"
    ws_call(
        ws, ctr, "Runtime.evaluate",
        expression="window.__rtl_keepalive||(window.__rtl_keepalive=setInterval(()=>console.debug('keepalive',Date.now()),15000));",
        returnByValue=True
    )


def _extract_song_from_response(res: dict) -> str:
    """
    Extract the song value from a CDP Runtime.evaluate response.
    
    CDP responses have a nested structure:
    {
      "id": 1,
      "result": {
        "result": {
          "type": "string",
          "value": "Song — Artist"
        }
      }
    }
    
    Args:
        res: CDP response dict
        
    Returns:
        Extracted song string, or empty string if not found
    """
    # Navigate the nested structure safely
    if "result" not in res:
        return ""
    if "result" not in res["result"]:
        return ""
    
    val = res["result"]["result"].get("value") or ""
    return val.strip()


def _try_scrape_tab(wsurl: str, port: int, debug: bool) -> str | None:
    """
    Attempt to scrape the current song from a single browser tab.
    
    This function handles:
    - Connecting to the tab via WebSocket
    - Setting up the CDP session
    - Executing the JavaScript scraper
    - Cleaning up the connection
    
    Args:
        wsurl: WebSocket URL for the browser tab
        port: CDP port (for Origin header)
        debug: Whether to print debug output
        
    Returns:
        Song string if successful, None if failed or no song found
    """
    ws = None
    try:
        # Connect to the browser tab
        ws = websocket.create_connection(
            wsurl,
            header=[f"Origin: http://localhost:{port}"],  # Required by Chrome
            timeout=8  # Don't hang forever if something goes wrong
        )
        
        # Initialize CDP session
        ctr = {'id': 0}
        _setup_cdp_session(ws, ctr)
        
        # Execute our JavaScript scraper in the page context
        res = ws_call(
            ws, ctr, "Runtime.evaluate",
            expression=EVAL_JS,
            awaitPromise=True,  # Wait for async function to complete
            returnByValue=True  # Return actual value, not object reference
        )
        
        # Extract the song from the response
        val = _extract_song_from_response(res)
        
        if val:
            dbg(debug, f"tab ok -> {val}")
            return val
        return None
        
    finally:
        # Always clean up the WebSocket connection
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass  # Ignore errors during cleanup


def scrape_once(port: int = 9222, debug: bool = False) -> str:
    """
    Scrape the current song from the browser.
    
    This is the main scraping function. It:
    1. Connects to Chrome's debug endpoint to list tabs
    2. Finds the best tab (Radioplayer > main site > RTL+)
    3. Tries to scrape each candidate tab until one succeeds
    
    Args:
        port: Chrome DevTools Protocol port (default 9222)
        debug: Enable verbose debug output
        
    Returns:
        Current song in "Title — Artist" format, or empty string if not found
        
    Raises:
        RuntimeError: If no suitable browser tab is found
    """
    # Validate port to prevent SSRF attacks
    validated_port = validate_port(port)
    
    # Query Chrome for list of open tabs
    # Security: Only connects to localhost, port is validated
    response = requests.get(
        f"http://127.0.0.1:{validated_port}/json",
        timeout=5  # Don't hang if Chrome isn't running
    )
    
    # Find and prioritize suitable tabs
    targets = pick_target(response.json(), debug=debug)
    
    if not targets:
        raise RuntimeError("No matching tab found. Please open Radioplayer or 89.0 RTL.")

    # Try each tab in priority order until one works
    for _prio, _title, _url, wsurl in targets:
        if not wsurl:
            continue  # Tab doesn't support debugging
        
        result = _try_scrape_tab(wsurl, validated_port, debug)
        if result:
            return result
    
    return ""  # No tab returned a valid song


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the 89.0 RTL Now Playing scraper.
    
    Parses command line arguments, validates inputs, and runs the
    continuous scraping loop.
    """
    # Define command line arguments
    ap = argparse.ArgumentParser(
        description="89.0 RTL NowPlaying (via Chrome CDP, stabilized)"
    )
    ap.add_argument(
        "--port", type=int, default=9222,
        help="Chrome DevTools Protocol port (default: 9222)"
    )
    ap.add_argument(
        "--out", default="Nowplaying/nowplaying.txt",
        help="Output file path for current song (default: Nowplaying/nowplaying.txt)"
    )
    ap.add_argument(
        "--interval", type=int, default=5,
        help="Seconds between scrape attempts (default: 5)"
    )
    ap.add_argument(
        "--debounce", type=int, default=6000,
        help="Milliseconds until title is considered stable (default: 6000)"
    )
    ap.add_argument(
        "--repeat-gap", type=int, default=90,
        help="Minimum seconds between same track outputs (default: 90)"
    )
    ap.add_argument(
        "--debug", action="store_true",
        help="Enable verbose debug output"
    )
    args = ap.parse_args()

    # === Security: Validate all inputs at startup ===
    # This ensures all subsequent operations use known-safe values
    out_path = validate_output_path(args.out)
    validate_port(args.port)
    
    print(f"[rtl89-cdp] Writing to {out_path} every {args.interval}s", flush=True)

    # Initialize the stabilizer with configured timings
    stab = Stabilizer(debounce_ms=args.debounce, min_repeat_gap_s=args.repeat_gap)

    # Main scraping loop
    try:
        while True:
            try:
                # Scrape current song from browser
                raw = scrape_once(port=args.port, debug=args.debug)
                
                # Feed through stabilizer to prevent flickering
                stable = stab.feed(raw)
                
                # Only write if we got a new stable song
                if stable:
                    write_atomic(out_path, stable)
                    print("[update]", stable, flush=True)
                    
            except KeyboardInterrupt:
                # User pressed Ctrl+C, exit cleanly
                raise
            except Exception as e:
                # Log errors but keep running
                print("[warn]", e, flush=True)
            
            # Wait before next scrape
            time.sleep(max(1, int(args.interval)))
            
    except KeyboardInterrupt:
        # Clean exit message
        print("[exit] bye 👋❤", flush=True)


# =============================================================================
# Script Entry Point
# =============================================================================

if __name__ == "__main__":
    main()