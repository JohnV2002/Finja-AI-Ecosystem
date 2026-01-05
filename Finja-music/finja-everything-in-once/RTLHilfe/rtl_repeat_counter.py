"""
======================================================================
                Finja's Brain & Knowledge Core - RTL Repeat Counter
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0 (RTL Module)

  ✨ New in 1.1.0:
    • Complete English documentation with docstrings
    • All comments and messages translated to English
    • Copyright updated to 2026
    • Fixed path traversal vulnerabilities (Snyk)
    • Added extensive inline comments for better code understanding

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Monitors a `nowplaying.txt` file for changes.
  • Counts the repetitions of each individual song.
  • Stores counts persistently in a JSON file (`repeat_counts.json`).
  • Writes the current repeat count to `obs_repeat.txt` for OBS display.
  • Cleans up created files on graceful exit.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os
import json
import time
import argparse
import signal
import sys
from pathlib import Path
from typing import Dict


# =============================================================================
# Default Configuration Paths
# =============================================================================

# These paths are relative to the script location by default
# Users can override them via command line arguments
DEFAULT_NP_PATH = r"..\Nowplaying\nowplaying.txt"
DEFAULT_OUT_DIR = r"..\Nowplaying"
DEFAULT_MEM_FILE = r"..\Memory\repeat_counts.json"


# =============================================================================
# Security Constants
# =============================================================================

# Only allow file operations within user's home directory or current working directory
# This prevents malicious path traversal attacks (e.g., --np "../../../etc/passwd")
ALLOWED_DIRS = [Path.home(), Path.cwd()]


# =============================================================================
# Global State for Signal Handling
# =============================================================================

# Flag to control the main loop - set to False by signal handler to trigger graceful shutdown
_running = True


def _sigint(_sig, _frm) -> None:
    """
    Signal handler for SIGINT (Ctrl+C).
    
    Sets the global _running flag to False, which causes the main loop
    to exit gracefully on the next iteration.
    
    Args:
        _sig: Signal number (unused but required by signal API)
        _frm: Current stack frame (unused but required by signal API)
    """
    global _running
    _running = False


# =============================================================================
# Security Validation Functions
# =============================================================================

def validate_path(path: str) -> Path:
    """
    Validate and sanitize a file path to prevent path traversal attacks.
    
    This function resolves the path to its absolute form and checks if it
    falls within allowed directories. This prevents attacks like:
    - --np "../../etc/passwd"
    - --outdir "/tmp/../../../etc"
    
    Args:
        path: The path string to validate
        
    Returns:
        Resolved absolute Path object that is safe to use
        
    Raises:
        ValueError: If path resolves to a location outside allowed directories
    """
    # resolve() follows symlinks and removes ".." components
    # This reveals the TRUE destination path
    resolved = Path(path).resolve()
    
    # Check if the resolved path is inside any allowed directory
    for allowed_dir in ALLOWED_DIRS:
        try:
            # relative_to() raises ValueError if path is not within allowed_dir
            resolved.relative_to(allowed_dir.resolve())
            return resolved  # Path is safe!
        except ValueError:
            # Not in this allowed directory, try the next one
            continue
    
    # Path is not in ANY allowed directory - reject it
    raise ValueError(f"Path not allowed: {resolved}")


# =============================================================================
# File I/O Functions
# =============================================================================

def write_atomic(path: Path, text: str) -> None:
    """
    Write text to file atomically using a temporary file.
    
    Atomic writing prevents data corruption if the process is interrupted mid-write.
    Instead of overwriting the file directly, we:
    1. Create parent directories if needed
    2. Write to a temporary file
    3. Rename the temp file to the target (atomic operation on most filesystems)
    
    This ensures the file always contains either the old OR new content, never partial.
    
    Args:
        path: Validated Path object (MUST be pre-validated!)
        text: Text content to write
        
    Security Note:
        The path parameter must be validated BEFORE calling this function.
        Validation happens at startup in main().
    """
    # Ensure parent directory exists
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # Directory might already exist or we might not have permissions
    
    # Create temp file path by appending .tmp to the full filename
    tmp = path.with_suffix(path.suffix + ".tmp")
    
    # Write to temp file first
    # Security: Path is pre-validated by validate_path() in main()
    with open(tmp, "w", encoding="utf-8") as f:  # nosec B108 - path is pre-validated
        # Strip whitespace and ensure single trailing newline
        f.write((text or "").strip() + "\n")
    
    # Atomic rename - on POSIX systems, rename() is atomic
    os.replace(tmp, path)  # nosec B108 - path is pre-validated


def read_text(path: Path) -> str:
    """
    Read text content from a file.
    
    Returns empty string if file doesn't exist or can't be read.
    This is intentional - we don't want to crash if the nowplaying.txt
    file hasn't been created yet by the scraper.
    
    Args:
        path: Validated Path object to read from
        
    Returns:
        File content as stripped string, or empty string on error
    """
    try:
        # Security: Path is pre-validated by validate_path() in main()
        with open(path, "r", encoding="utf-8") as f:  # nosec B108 - path is pre-validated
            return f.read().strip()
    except Exception:
        # File doesn't exist yet, or permission denied, etc.
        return ""


def load_counts(mem_file: Path) -> Dict[str, int]:
    """
    Load song repeat counts from a JSON file.
    
    The JSON structure is simple: {"Song — Artist": count, ...}
    
    Args:
        mem_file: Validated Path to the counts JSON file
        
    Returns:
        Dictionary mapping song strings to their repeat counts.
        Returns empty dict if file doesn't exist or is invalid.
    """
    try:
        # Security: Path is pre-validated by validate_path() in main()
        with open(mem_file, "r", encoding="utf-8") as f:  # nosec B108 - path is pre-validated
            data = json.load(f)
            
            # Defensive validation: ensure we got a dict with correct types
            if isinstance(data, dict):
                # Cast keys to str and values to int for type safety
                return {str(k): int(v) for k, v in data.items()}
    except FileNotFoundError:
        # File doesn't exist yet - that's fine, we'll create it
        pass
    except json.JSONDecodeError:
        # File exists but contains invalid JSON - start fresh
        print("[warn] Invalid JSON in counts file, starting fresh", flush=True)
    except Exception as e:
        # Unexpected error - log it but continue
        print(f"[warn] Error loading counts: {e}", flush=True)
    
    return {}


def save_counts(mem_file: Path, counts: Dict[str, int]) -> None:
    """
    Save song repeat counts to a JSON file atomically.
    
    Uses atomic writing to prevent data corruption.
    
    Args:
        mem_file: Validated Path for the counts JSON file
        counts: Dictionary mapping song strings to their repeat counts
    """
    # Ensure parent directory exists
    try:
        mem_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    
    # Create temp file for atomic write
    tmp = mem_file.with_suffix(mem_file.suffix + ".tmp")
    
    # Write JSON with pretty formatting for human readability
    # Security: Path is pre-validated by validate_path() in main()
    with open(tmp, "w", encoding="utf-8") as f:  # nosec B108 - path is pre-validated
        json.dump(counts, f, ensure_ascii=False, indent=2)
    
    # Atomic rename
    os.replace(tmp, mem_file)  # nosec B108 - path is pre-validated


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the RTL Repeat Counter.
    
    This script watches a nowplaying.txt file for changes and counts
    how many times each song has been played. The count is written to
    obs_repeat.txt for display in OBS overlays.
    
    The counts are persisted to a JSON file so they survive restarts.
    """
    # Define command line arguments
    ap = argparse.ArgumentParser(
        description="Count repeats of nowplaying.txt and expose to obs_repeat.txt"
    )
    ap.add_argument(
        "--np", default=DEFAULT_NP_PATH,
        help="Path to nowplaying.txt (default: ../Nowplaying/nowplaying.txt)"
    )
    ap.add_argument(
        "--outdir", default=DEFAULT_OUT_DIR,
        help="Output directory for obs_* files (default: ../Nowplaying)"
    )
    ap.add_argument(
        "--memfile", default=DEFAULT_MEM_FILE,
        help="JSON file for persistent repeat counts (default: ../Memory/repeat_counts.json)"
    )
    ap.add_argument(
        "--interval", type=int, default=2,
        help="Poll interval in seconds (default: 2)"
    )
    args = ap.parse_args()

    # === Security: Validate all paths at startup ===
    # This ensures all subsequent file operations use known-safe paths
    np_path = validate_path(args.np)
    out_dir = validate_path(args.outdir)
    mem_file = validate_path(args.memfile)
    
    # Ensure interval is at least 1 second to prevent CPU spinning
    interval = max(1, int(args.interval))
    
    # Build output file path for OBS repeat display
    out_repeat = out_dir / "obs_repeat.txt"

    # Create necessary directories
    out_dir.mkdir(parents=True, exist_ok=True)
    mem_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"[repeat] Watching {np_path} every {interval}s", flush=True)

    # Register signal handler for graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, _sigint)
    
    # Track the last seen song to detect changes
    last_seen = ""
    
    # Load existing counts from persistent storage
    counts = load_counts(mem_file)

    try:
        # === Main monitoring loop ===
        while _running:
            # Read current song from nowplaying.txt
            cur = read_text(np_path)

            # Only process if we have content and it's different from last time
            if cur and cur != last_seen:
                # Validate format: must contain " — " (em-dash with spaces)
                # This is the format our scraper outputs: "Title — Artist"
                if " — " in cur:
                    # Increment count for this song
                    counts[cur] = int(counts.get(cur, 0)) + 1
                    
                    # Persist updated counts to disk
                    save_counts(mem_file, counts)
                    
                    # Write current count to OBS display file
                    write_atomic(out_repeat, f"Song Repeat: {counts[cur]}×")
                    
                    # Log to console
                    print(f"[repeat] {cur} -> {counts[cur]}×", flush=True)
                else:
                    # Format doesn't match expected pattern
                    # This might be station jingles, ads, or errors
                    # Hide the badge by writing empty content
                    write_atomic(out_repeat, "")
                
                # Update last seen regardless of format
                last_seen = cur

            # Wait before next poll
            time.sleep(interval)
            
    finally:
        # === Cleanup on exit ===
        # This runs whether we exit normally or via Ctrl+C
        
        # Remove the memory file (start fresh next time)
        # This is intentional - counts are session-based
        try:
            if mem_file.exists():
                mem_file.unlink()
        except Exception:
            pass
        
        # Clear the OBS display file
        try:
            write_atomic(out_repeat, "")
        except Exception:
            pass
        
        print("[repeat] bye 👋❤", flush=True)
        sys.exit(0)


# =============================================================================
# Script Entry Point
# =============================================================================

if __name__ == "__main__":
    main()