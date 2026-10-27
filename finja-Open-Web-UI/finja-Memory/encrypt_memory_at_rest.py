"""
======================================================================
         Finja Cloud Memory – Encrypt at Rest Utility
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-cloud-memory / encrypt-at-rest
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 4.5.1

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the Apache License 2.0

  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Encrypts existing finja-Memory user memory JSON files at rest
  using AES-256-GCM. Run inside the memory-server directory after
  setting the FINJA_DATA_ENCRYPTION_KEY environment variable:

      python encrypt_memory_at_rest.py

  • Scans all *_memory.json files in the user_memories/ directory.
  • Already-encrypted files are re-encrypted (key rotation safe).
  • Validates JSON integrity before writing the encrypted version.
  • Produces a summary with OK / FAIL counts.

 New in 4.5.0:
  • Fix: uses the server's file header FINJAENC1 (it wrote "KEY\n", a
    format the server reads as broken JSON, so the next save would have
    replaced those memories with an empty list).
  • Real key rotation: FINJA_DATA_ENCRYPTION_KEY_OLD decrypts, the new
    FINJA_DATA_ENCRYPTION_KEY encrypts; files already on the new key are
    left as they are, so a second run is harmless.
  • --check validates every file without writing; --include-backups also
    rotates the memory files under backups/.
  • Reads private/.env (then .env); paths are relative to this script.

======================================================================
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "private" / ".env")
load_dotenv(BASE_DIR / ".env")

MAGIC = b"FINJAENC1\n"  # must match memory-server.py ENCRYPTION_MAGIC
NONCE_SIZE = 12
USER_MEMORY_DIR = BASE_DIR / "user_memories"
BACKUP_DIR = BASE_DIR / "backups"


def _b64decode_unpadded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def key_bytes(raw: str) -> bytes:
    """Same derivation as the server: a base64 16/24/32-byte key, otherwise SHA-256 of the text."""
    raw = raw.strip()
    try:
        decoded = _b64decode_unpadded(raw)
        if len(decoded) in {16, 24, 32}:
            return decoded
    except ValueError:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def decrypt_any(data: bytes, keys: list[bytes]) -> tuple[bytes, int | None]:
    """Plaintext stays as it is; otherwise the index of the key that opened it."""
    if not data.startswith(MAGIC):
        return data, None
    payload = data[len(MAGIC):]
    if len(payload) <= NONCE_SIZE:
        raise ValueError("encrypted file is truncated")
    for index, key in enumerate(keys):
        try:
            return AESGCM(key).decrypt(payload[:NONCE_SIZE], payload[NONCE_SIZE:], None), index
        except InvalidTag:
            continue
    raise ValueError("no configured key opens this file")


def encrypt(data: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_SIZE)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, None)


def memory_files(include_backups: bool) -> list[Path]:
    files = sorted(p for p in USER_MEMORY_DIR.glob("*_memory.json") if p.is_file()) if USER_MEMORY_DIR.exists() else []
    if include_backups and BACKUP_DIR.exists():
        files += sorted(p for p in BACKUP_DIR.rglob("*.json") if p.is_file())
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encrypt or re-key the memory files at rest.")
    parser.add_argument("--check", action="store_true", help="validate every file, write nothing")
    parser.add_argument("--include-backups", action="store_true", help="also handle *.json under backups/")
    args = parser.parse_args(argv)

    new_raw = os.getenv("FINJA_DATA_ENCRYPTION_KEY", "")
    if not new_raw.strip():
        print("FAIL FINJA_DATA_ENCRYPTION_KEY is not set")
        return 2
    new_key = key_bytes(new_raw)
    old_raw = os.getenv("FINJA_DATA_ENCRYPTION_KEY_OLD", "")
    keys = [new_key] + ([key_bytes(old_raw)] if old_raw.strip() else [])

    counts = {"total": 0, "encrypted": 0, "rekeyed": 0, "unchanged": 0, "failed": 0}
    for path in memory_files(args.include_backups):
        counts["total"] += 1
        try:
            raw = path.read_bytes()
            plain, opened_with = decrypt_any(raw, keys)
            json.loads(plain.decode("utf-8"))  # never replace a file whose content is not valid JSON
            if opened_with == 0:
                counts["unchanged"] += 1
                continue
            action = "encrypted" if opened_with is None else "rekeyed"
            counts[action] += 1
            if not args.check:
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_bytes(encrypt(plain, new_key))
                os.replace(tmp, path)
            print(f"OK {'would be ' if args.check else ''}{action} {path.relative_to(BASE_DIR)}")
        except (OSError, ValueError) as exc:
            counts["failed"] += 1
            print(f"FAIL {path.relative_to(BASE_DIR)}: {type(exc).__name__}: {exc}")

    print("SUMMARY " + " ".join(f"{k}={v}" for k, v in counts.items()) + (" (check only)" if args.check else ""))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
