"""
YourAI App Upload Helpers
========================
Validation, storage, serving, and age-based cleanup for temporary mobile image
uploads used during chat interactions.

Main Responsibilities:
- Validate MIME-type and size constraints for incoming user uploads.
- Save temporary files securely using randomly generated UUIDs.
- Serve temporary images with caching headers.
- Perform automated cleanup of expired uploads (older than 1 hour).

Side Effects:
- Modifies and manages files in temp_uploads/ directory.
- Logs file I/O operations and errors to the debug console using YourAIUploadError.
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid as _uuid_mod
from pathlib import Path

import anyio

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUploadError

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_UPLOADS_DIR = os.path.join(_ROOT_DIR, "temp_uploads")

UPLOAD_MAX_AGE = 3600
UPLOAD_MAX_SIZE = 10 * 1024 * 1024
MIME_JPEG = "image/jpeg"
MIME_PNG = "image/png"
MIME_GIF = "image/gif"
MIME_WEBP = "image/webp"

UPLOAD_ALLOWED = {MIME_JPEG, MIME_PNG, MIME_GIF, MIME_WEBP}
# Extension strings are fixed constants only (never raw user input in joins).
UPLOAD_EXTS = {
    MIME_JPEG: "jpg",
    MIME_PNG: "png",
    MIME_GIF: "gif",
    MIME_WEBP: "webp",
}
TEMP_MEDIA_TYPES = {
    "jpg": MIME_JPEG,
    "png": MIME_PNG,
    "gif": MIME_GIF,
    "webp": MIME_WEBP,
}
_EXT_BY_CODE = {
    0: "jpg",
    1: "png",
    2: "gif",
    3: "webp",
}
_CODE_BY_EXT = {v: k for k, v in _EXT_BY_CODE.items()}

# User-provided names must match this grammar before we parse UUID + ext code.
_SAFE_TEMP_NAME = re.compile(
    r"^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\.(jpg|png|gif|webp)$"
)


def _temp_base() -> Path:
    return Path(TEMP_UPLOADS_DIR).resolve()


def _ext_code(ext: str) -> int | None:
    return _CODE_BY_EXT.get(ext)


def _path_for_id_and_code(file_id: _uuid_mod.UUID, ext_code: int) -> Path:
    """Build absolute path using only UUID.int + integer ext code (no user strings)."""
    ext = _EXT_BY_CODE.get(ext_code)
    if ext is None:
        raise HTTPException(status_code=404, detail="Not found")
    # Rebuild UUID from integer bits only — breaks taint from request text.
    clean = _uuid_mod.UUID(int=file_id.int)
    base = _temp_base()
    # Path segments are only: base (constant) + f"{clean}.{ext}" where both
    # parts come from library/constants, not the request string.
    name = f"{clean}.{ext}"
    full = os.path.normpath(os.path.join(str(base), name))
    base_s = str(base)
    if full != base_s and not full.startswith(base_s + os.sep):
        raise HTTPException(status_code=404, detail="Not found")
    return Path(full)


def _parse_request_name(filename: str) -> tuple[_uuid_mod.UUID, int]:
    """Parse request filename into (UUID, ext_code) or 404."""
    match = _SAFE_TEMP_NAME.fullmatch(filename or "")
    if match is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        file_id = _uuid_mod.UUID(match.group(1))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    code = _ext_code(match.group(2))
    if code is None:
        raise HTTPException(status_code=404, detail="Not found")
    return file_id, code


def cleanup_temp_uploads() -> None:
    """Delete temp uploads older than UPLOAD_MAX_AGE."""
    if not os.path.isdir(TEMP_UPLOADS_DIR):
        return

    now = time.time()
    base = _temp_base()
    try:
        names = os.listdir(str(base))
    except OSError:
        return

    for name in names:
        try:
            # Validate grammar, then rebuild path from UUID.int + ext code only.
            file_id, code = _parse_request_name(name)
        except HTTPException:
            continue
        try:
            path = _path_for_id_and_code(file_id, code)
            if path.is_file() and now - path.stat().st_mtime > UPLOAD_MAX_AGE:
                path.unlink()
        except (OSError, HTTPException) as e:
            err = YourAIUploadError(
                "cleanup failed", filename=name, cause=e, module="app_uploads"
            )
            log_exception("APP_UPLOADS", err)


def _ext_for_content_type(content_type: str, filename: str | None) -> str:
    """Map MIME type to fixed extension constant."""
    content_type = (content_type or "").lower()
    if content_type not in UPLOAD_ALLOWED:
        err = YourAIUploadError(
            f"unsupported type: {content_type}",
            filename=filename,
            module="app_uploads",
        )
        log_exception("APP_UPLOADS", err)
        raise HTTPException(
            status_code=415,
            detail="Only images allowed (jpeg/png/gif/webp)",
        )
    return UPLOAD_EXTS[content_type]


async def save_mobile_upload(file: UploadFile) -> dict:
    """
    Validate type/size, store under a server-generated UUID name, return metadata.
    """
    ext = _ext_for_content_type(file.content_type or "", file.filename)
    data = await file.read()

    if len(data) > UPLOAD_MAX_SIZE:
        err = YourAIUploadError(
            "file too large",
            filename=file.filename,
            size=len(data),
            limit=UPLOAD_MAX_SIZE,
            module="app_uploads",
        )
        log_exception("APP_UPLOADS", err)
        raise HTTPException(
            status_code=413,
            detail=f"Image too large (max {UPLOAD_MAX_SIZE // (1024 * 1024)} MB)",
        )

    os.makedirs(TEMP_UPLOADS_DIR, exist_ok=True)
    cleanup_temp_uploads()

    # Entirely server-generated identity (not derived from client filename).
    file_id = _uuid_mod.uuid4()
    code = _ext_code(ext)
    if code is None:
        raise HTTPException(status_code=415, detail="Only images allowed (jpeg/png/gif/webp)")
    filepath = _path_for_id_and_code(file_id, code)
    filename = filepath.name

    try:
        await anyio.Path(os.fspath(filepath)).write_bytes(data)
    except OSError as e:
        err = YourAIUploadError("disk write failed", filename=filename, cause=e, module="app_uploads")
        log_exception("APP_UPLOADS", err)
        raise HTTPException(status_code=500, detail="Error saving upload") from e

    log("APP_UPLOADS", f"Mobile upload: {filename} ({len(data) // 1024} KB)", Fore.CYAN)
    return {
        "ok": True,
        "url": f"/api/mobile/temp/{filename}",
        "filename": filename,
        "size": len(data),
    }


def serve_temp_upload(filename: str) -> FileResponse:
    """Serve a previously uploaded temp image if the name is valid and on disk."""
    file_id, code = _parse_request_name(filename)
    filepath = _path_for_id_and_code(file_id, code)
    if not filepath.is_file():
        raise HTTPException(
            status_code=404,
            detail="Image no longer available (expired or never uploaded)",
        )
    ext = _EXT_BY_CODE[code]
    return FileResponse(
        os.fspath(filepath),
        media_type=TEMP_MEDIA_TYPES[ext],
        headers={"Cache-Control": "no-store"},
    )
