"""
======================================================================
         Finja Cloud Memory – Encrypt at Rest Utility
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-cloud-memory / encrypt-at-rest
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 4.4.5

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

======================================================================
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv()

MAGIC = b"KEY\n"
NONCE_SIZE = 12
USER_MEMORY_DIR = Path("user_memories")
BACKUP_DIR = Path("backups")


def _b64decode_unpadded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _key_bytes() -> bytes:
    raw = os.getenv("FINJA_DATA_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise RuntimeError("FINJA_DATA_ENCRYPTION_KEY is not set")
    try:
        decoded = _b64decode_unpadded(raw)
        if len(decoded) in {16, 24, 32}:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _decrypt_or_plain(data: bytes, key: bytes) -> bytes:
    if not data.startswith(MAGIC):
        return data
    payload = data[len(MAGIC):]
    if len(payload) <= NONCE_SIZE:
        raise RuntimeError("encrypted file is truncated")
    return AESGCM(key).decrypt(payload[:NONCE_SIZE], payload[NONCE_SIZE:], None)


def _encrypt(data: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_SIZE)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, None)


def _iter_files() -> list[Path]:
    if not USER_MEMORY_DIR.exists():
        return []
    return sorted(p for p in USER_MEMORY_DIR.glob("*_memory.json") if p.is_file())


def main() -> int:
    key = _key_bytes()
    total = 0
    migrated = 0
    already = 0
    failed = 0

    for path in _iter_files():
        total += 1
        try:
            raw = path.read_bytes()
            was_encrypted = raw.startswith(MAGIC)
            if was_encrypted:
                already += 1
            plain = _decrypt_or_plain(raw, key)
            # Validate JSON before replacing the file.
            json.loads(plain.decode("utf-8"))
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(_encrypt(plain, key))
            os.replace(tmp, path)
            migrated += 1
            print(f"OK {'reencrypted' if was_encrypted else 'encrypted'} {path}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {path}: {type(exc).__name__}: {exc}")

    print(f"SUMMARY total={total} migrated={migrated} already_encrypted={already} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

