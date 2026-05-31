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

import os
import sys
import time
import uuid as _uuid_mod
import anyio

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUploadError
from helpers.text_parser import is_temp_upload_filename

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_UPLOADS_DIR = os.path.join(_ROOT_DIR, "temp_uploads")

UPLOAD_MAX_AGE = 3600
UPLOAD_MAX_SIZE = 10 * 1024 * 1024
MIME_JPEG = "image/jpeg"
MIME_PNG = "image/png"
MIME_GIF = "image/gif"
MIME_WEBP = "image/webp"

UPLOAD_ALLOWED = {MIME_JPEG, MIME_PNG, MIME_GIF, MIME_WEBP}
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


def cleanup_temp_uploads() -> None:
    """
    Deletes temporary uploaded files from disk that exceed UPLOAD_MAX_AGE (1 hour).

    Returns:
        None.
    """
    if not os.path.isdir(TEMP_UPLOADS_DIR):
        return

    now = time.time()
    for fname in os.listdir(TEMP_UPLOADS_DIR):
        fpath = os.path.join(TEMP_UPLOADS_DIR, fname)
        try:
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > UPLOAD_MAX_AGE:
                os.unlink(fpath)
        except OSError as e:
            err = YourAIUploadError("cleanup failed", filename=fname, cause=e, module="app_uploads")
            log_exception("APP_UPLOADS", err)


def _ext_for_content_type(content_type: str, filename: str | None) -> str:
    """
    Maps an incoming MIME content-type to its corresponding file extension, 
    raising an error if the type is unsupported.

    Args:
        content_type (str): The MIME content-type of the uploaded file.
        filename (str | None): The original uploaded file name (for logging context).

    Raises:
        HTTPException: 415 if the content-type is not in the allowed set.

    Returns:
        str: The mapped file extension string (e.g. "jpg").
    """
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
            detail=f"Only images allowed (jpeg/png/gif/webp), received: {content_type}",
        )
    return UPLOAD_EXTS[content_type]


async def save_mobile_upload(file: UploadFile) -> dict:
    """
    Validates an uploaded file's type and size, triggers cache cleanup,
    saves the file securely using a random UUID filename, and returns the response metadata.

    Args:
        file (UploadFile): The uploaded file instance.

    Raises:
        HTTPException: 413 if the file size exceeds UPLOAD_MAX_SIZE (10MB),
                       500 if writing the file to disk fails.

    Returns:
        dict: A metadata dictionary containing success status, URL path, filename, and size.
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

    filename = f"{_uuid_mod.uuid4()}.{ext}"
    filepath = os.path.join(TEMP_UPLOADS_DIR, filename)
    try:
        await anyio.Path(filepath).write_bytes(data)
    except OSError as e:
        err = YourAIUploadError("disk write failed", filename=filename, cause=e, module="app_uploads")
        log_exception("APP_UPLOADS", err)
        raise HTTPException(status_code=500, detail="Error saving upload")

    log("APP_UPLOADS", f"Mobile upload: {filename} ({len(data) // 1024} KB)", Fore.CYAN)
    return {
        "ok": True,
        "url": f"/api/mobile/temp/{filename}",
        "filename": filename,
        "size": len(data),
    }


def serve_temp_upload(filename: str) -> FileResponse:
    """
    Validates the requested filename format, verifies its existence, 
    and serves it using a FileResponse with caching disabled.

    Args:
        filename (str): The filename of the temporary image to serve.

    Raises:
        HTTPException: 404 if the filename format is invalid or the file is missing/expired.

    Returns:
        FileResponse: The FastAPI file response serving the requested image.
    """
    if not is_temp_upload_filename(filename):
        raise HTTPException(status_code=404, detail="Not found")

    filepath = os.path.join(TEMP_UPLOADS_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Image no longer available (expired or never uploaded)")

    ext = filename.rsplit(".", 1)[-1]
    return FileResponse(
        filepath,
        media_type=TEMP_MEDIA_TYPES[ext],
        headers={"Cache-Control": "no-store"},
    )
