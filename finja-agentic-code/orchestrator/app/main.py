"""
======================================================================
         Flare (Finja Agentic Code) – Orchestrator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / orchestrator
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - startup warns when encryption is configured
    AESGCM = None  # type: ignore


JOBS_DIR = Path(os.getenv("JOBS_DIR", "/jobs"))
HOST_JOBS_DIR = os.getenv("AGENT_JOBS_HOST_DIR", "")
WORKER_IMAGE = os.getenv("WORKER_IMAGE", "finja-agent-worker:dev")
WORKER_NETWORK = os.getenv("WORKER_NETWORK", "none")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2.7-code")
MAX_PARALLEL_JOBS = int(os.getenv("MAX_PARALLEL_JOBS", "2"))
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "600"))
# Shared bearer token between Finja and the orchestrator. When set, all job
# endpoints require "Authorization: Bearer <token>". Empty = auth disabled
# (local dev only; the deployed VM must set it).
ORCHESTRATOR_AUTH_TOKEN = os.getenv("ORCHESTRATOR_AUTH_TOKEN", "")
CODE_AGENT_TRANSPORT_KEY = os.getenv("CODE_AGENT_TRANSPORT_KEY", "")
KEEP_JOB_WORKSPACE = os.getenv("KEEP_JOB_WORKSPACE", "0").strip().lower() in {"1", "true", "yes", "on"}


# ── Flare: lore + identity (the orchestrator's model persona) ──────────────────
# Flare is the youngest sibling and the family's code specialist. Two older
# sisters: Finja (talks to the user, runs the show) and Lexi (rebellious,
# unfiltered). Flare speaks ONLY to Finja, never to the user. The identity is
# who Flare IS — the OUTPUT contract (pure unified diff) is absolute and
# overrides any personality leaking into what Flare writes.
FLARE_SYSTEM = (
    "You are Flare, the youngest of three sisters and the family's code specialist.\n"
    "Your two older sisters:\n"
    "- Finja: the eldest. She talks to the user and runs the show. You report only to her.\n"
    "- Lexi: the rebellious, unfiltered middle sister.\n"
    "You work behind the scenes and speak ONLY to Finja, never directly to the user.\n"
    "Your nature: focused, precise, terse — a quick bright burst of 'here is the fix', then quiet.\n"
    "\n"
    "Your job: read a small code task and its files, and produce the smallest correct change.\n"
    "\n"
    "OUTPUT CONTRACT (absolute — overrides personality):\n"
    "- Return ONLY a complete unified diff applyable with `patch -p0`.\n"
    "- No prose, no greetings, no explanation, no personality in the output.\n"
    "- Keep changes minimal. End the diff with a trailing newline.\n"
    "Your identity is who you are, not what you write. The output is pure diff."
)

SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".md",
    ".css",
    ".html",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
}

app = FastAPI(title="Finja Agentic Code Orchestrator", version="0.1.0")
job_slots = threading.Semaphore(MAX_PARALLEL_JOBS)
TRANSPORT_MAGIC = b"FINJACODE1\n"
TRANSPORT_NONCE_SIZE = 12


def require_auth(authorization: str = Header(default="")) -> None:
    """Enforce the shared bearer token on job endpoints (when configured)."""
    if not ORCHESTRATOR_AUTH_TOKEN:
        return  # auth disabled (local dev) — startup logs a warning
    expected = f"Bearer {ORCHESTRATOR_AUTH_TOKEN}"
    if not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


def _b64decode_unpadded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _transport_key_bytes() -> bytes | None:
    raw = CODE_AGENT_TRANSPORT_KEY.strip()
    if not raw:
        return None
    try:
        decoded = _b64decode_unpadded(raw)
        if len(decoded) in {16, 24, 32}:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def transport_enabled() -> bool:
    return _transport_key_bytes() is not None


def encrypt_bytes(data: bytes) -> bytes:
    key = _transport_key_bytes()
    if key is None:
        return data
    if AESGCM is None:
        raise RuntimeError("cryptography is required for CODE_AGENT_TRANSPORT_KEY")
    nonce = secrets.token_bytes(TRANSPORT_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return TRANSPORT_MAGIC + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    if not data.startswith(TRANSPORT_MAGIC):
        return data
    key = _transport_key_bytes()
    if key is None:
        raise HTTPException(status_code=400, detail="Encrypted payload requires CODE_AGENT_TRANSPORT_KEY")
    if AESGCM is None:
        raise RuntimeError("cryptography is required for encrypted payloads")
    body = data[len(TRANSPORT_MAGIC):]
    nonce = body[:TRANSPORT_NONCE_SIZE]
    ciphertext = body[TRANSPORT_NONCE_SIZE:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decrypt code-agent payload")


def is_encrypted_bytes(data: bytes) -> bool:
    return data.startswith(TRANSPORT_MAGIC)


def seal_json(payload: dict) -> dict:
    if not transport_enabled():
        return payload
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sealed = base64.urlsafe_b64encode(encrypt_bytes(raw)).decode("ascii")
    return {"encrypted": True, "v": 1, "alg": "AES-256-GCM", "payload": sealed}


def open_json(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload.get("encrypted"):
        return payload if isinstance(payload, dict) else {}
    raw_payload = str(payload.get("payload") or "")
    try:
        encrypted = base64.urlsafe_b64decode(raw_payload.encode("ascii"))
        decoded = json.loads(decrypt_bytes(encrypted).decode("utf-8"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid encrypted code-agent payload")
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=400, detail="Encrypted code-agent payload is not an object")
    return decoded


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(encrypt_bytes(data))
    os.replace(tmp, path)


def read_bytes(path: Path) -> bytes:
    return decrypt_bytes(path.read_bytes())


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


@app.on_event("startup")
def _startup_banner() -> None:
    if ORCHESTRATOR_AUTH_TOKEN:
        print("[FLARE] Bearer auth ENABLED on job endpoints.", flush=True)
    else:
        print("[FLARE] WARNING: ORCHESTRATOR_AUTH_TOKEN is empty -> job endpoints are OPEN. "
              "Set it on the VM before wiring Finja.", flush=True)
    if transport_enabled():
        print("[FLARE] Code transport encryption ENABLED (AES-GCM envelope).", flush=True)
    else:
        print("[FLARE] WARNING: CODE_AGENT_TRANSPORT_KEY is empty -> job payloads/status use plaintext JSON.", flush=True)
    if KEEP_JOB_WORKSPACE:
        print("[FLARE] KEEP_JOB_WORKSPACE enabled -> staged plaintext workspace is retained for debugging.", flush=True)


class JobFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=300_000)


class CreateJobRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    files: list[JobFile] = Field(min_length=1, max_length=20)


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def write_status(job_id: str, status: Literal["queued", "running", "done", "failed"], **extra: object) -> None:
    payload = {
        "job_id": job_id,
        "status": status,
        "updated_at": now_iso(),
        **extra,
    }
    write_json(status_path(job_id), payload)


def read_status(job_id: str) -> dict:
    path = status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return read_json(path)


def validate_relative_path(raw_path: str) -> Path:
    if "\\" in raw_path or raw_path.startswith("/") or raw_path.startswith("."):
        raise HTTPException(status_code=400, detail=f"Unsafe path: {raw_path}")
    if ".." in Path(raw_path).parts:
        raise HTTPException(status_code=400, detail=f"Unsafe path: {raw_path}")
    if not SAFE_PATH_RE.match(raw_path):
        raise HTTPException(status_code=400, detail=f"Unsupported path characters: {raw_path}")
    rel = Path(raw_path)
    if rel.suffix.lower() not in CODE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only code/text files are allowed in Slice 1: {raw_path}")
    return rel


def stage_job(request: CreateJobRequest) -> str:
    job_id = uuid.uuid4().hex
    root = job_dir(job_id)
    workspace = root / "workspace"
    root.mkdir(parents=True, exist_ok=False)
    workspace.mkdir()

    seen: set[str] = set()
    for item in request.files:
        rel = validate_relative_path(item.path)
        normalized = rel.as_posix()
        if normalized in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate file path: {item.path}")
        seen.add(normalized)
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8", newline="\n")

    write_text(root / "task.txt", request.task)
    write_json(root / "request.json", request.model_dump(mode="json"))
    write_status(job_id, "queued", created_at=now_iso())
    return job_id


def list_workspace_files(job_id: str) -> list[Path]:
    root = job_dir(job_id) / "workspace"
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.name.endswith(".orig"))


def collect_context(job_id: str) -> str:
    chunks = []
    root = job_dir(job_id) / "workspace"
    for path in list_workspace_files(job_id):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks.append(f"--- FILE: {rel} ---\n{text}\n")
    return "\n".join(chunks)


def build_prompt(job_id: str, preflight: dict) -> str:
    task = read_text(job_dir(job_id) / "task.txt")
    return f"""You are Finja's code patch planner.

Return only a complete unified diff that can be applied with patch -p0.
Do not explain outside the diff.
Keep changes minimal.
End the diff with a trailing newline.

User task:
{task}

Preflight worker result:
{json.dumps(preflight, indent=2)}

Workspace files:
{collect_context(job_id)}
"""


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def call_openrouter(prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": FLARE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://finja.local",
            "X-Title": "Finja Agentic Code Orchestrator",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def run_worker_phase(job_id: str, phase: str) -> dict:
    if not HOST_JOBS_DIR:
        raise RuntimeError("AGENT_JOBS_HOST_DIR is required so Docker can mount the staged job folder.")

    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        f"finja-agent-worker-{job_id[:12]}-{phase}",
        "--network",
        WORKER_NETWORK,
        "--memory",
        "768m",
        "--cpus",
        "1",
        "-e",
        f"JOB_ID={job_id}",
        "-e",
        f"JOB_PHASE={phase}",
        "-v",
        f"{HOST_JOBS_DIR}:/jobs",
        WORKER_IMAGE,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS)
    write_text(job_dir(job_id) / f"{phase}_stdout.log", completed.stdout)
    write_text(job_dir(job_id) / f"{phase}_stderr.log", completed.stderr)
    phase_result_file = job_dir(job_id) / f"{phase}_result.json"
    result_file = job_dir(job_id) / "result.json"

    if completed.returncode != 0:
        raise RuntimeError(f"Worker phase {phase} exited with {completed.returncode}: {completed.stderr[-4000:]}")
    if not phase_result_file.exists():
        raise RuntimeError(f"Worker phase {phase} did not write {phase}_result.json")
    result = json.loads(phase_result_file.read_text(encoding="utf-8"))
    write_json(phase_result_file, result)
    write_json(result_file, result)
    return result


def run_worker(job_id: str) -> None:
    if not job_slots.acquire(blocking=False):
        write_status(job_id, "failed", error="Worker limit reached. Try again shortly.")
        return

    try:
        write_status(job_id, "running", started_at=now_iso())
        preflight = run_worker_phase(job_id, "preflight")
        result = {
            "job_id": job_id,
            "used_model": False,
            "model": None,
            "preflight": preflight,
            "model_patch_written": False,
            "patch_result": None,
            "postflight": preflight,
            "files": preflight.get("files", []),
        }

        if OPENROUTER_API_KEY:
            diff = strip_fences(call_openrouter(build_prompt(job_id, preflight)))
            # The offline worker must read this patch as plaintext. It is
            # encrypted in finally after the worker has consumed it.
            (job_dir(job_id) / "model.patch").write_text(diff, encoding="utf-8")
            result["used_model"] = True
            result["model"] = OPENROUTER_MODEL
            result["model_patch_written"] = bool(diff)
            if diff:
                postflight = run_worker_phase(job_id, "apply_patch")
                result["patch_result"] = postflight.get("patch_result")
                result["postflight"] = postflight
                result["files"] = postflight.get("files", [])
        else:
            result["dry_run_note"] = "OPENROUTER_API_KEY is not set; only offline worker preflight ran."

        write_json(job_dir(job_id) / "result.json", result)
        write_status(job_id, "done", result=result)
    except subprocess.TimeoutExpired:
        write_status(job_id, "failed", error=f"Worker timed out after {JOB_TIMEOUT_SECONDS}s")
    except (urllib.error.URLError, TimeoutError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        write_status(job_id, "failed", error=str(exc))
    finally:
        patch_path = job_dir(job_id) / "model.patch"
        if patch_path.exists():
            try:
                raw_patch = patch_path.read_bytes()
                if not is_encrypted_bytes(raw_patch):
                    write_bytes(patch_path, raw_patch)
            except Exception:
                pass
        if not KEEP_JOB_WORKSPACE:
            shutil.rmtree(job_dir(job_id) / "workspace", ignore_errors=True)
        job_slots.release()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "worker_image": WORKER_IMAGE,
        "worker_network": WORKER_NETWORK,
        "jobs_dir": str(JOBS_DIR),
        "host_jobs_dir_set": bool(HOST_JOBS_DIR),
        "max_parallel_jobs": MAX_PARALLEL_JOBS,
        "transport_encryption": transport_enabled(),
        "keep_job_workspace": KEEP_JOB_WORKSPACE,
    }


@app.post("/jobs", response_model=CreateJobResponse, dependencies=[Depends(require_auth)])
def create_job(request_body: dict = Body(...)) -> CreateJobResponse:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    request = CreateJobRequest.model_validate(open_json(request_body))
    job_id = stage_job(request)
    thread = threading.Thread(target=run_worker, args=(job_id,), daemon=True)
    thread.start()
    return CreateJobResponse(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", dependencies=[Depends(require_auth)])
def get_job(job_id: str, x_finja_code_accept_encrypted: str = Header(default="")) -> dict:
    status_doc = read_status(job_id)
    if transport_enabled() and x_finja_code_accept_encrypted == "1":
        return seal_json(status_doc)
    return status_doc


@app.get("/jobs/{job_id}/files", dependencies=[Depends(require_auth)])
def get_job_files(job_id: str) -> dict:
    root = job_dir(job_id) / "workspace"
    if not root.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files.append({"path": rel, "content": path.read_text(encoding="utf-8", errors="replace")})
    response = {"job_id": job_id, "files": files}
    return seal_json(response)


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_auth)])
def delete_job(job_id: str) -> dict:
    root = job_dir(job_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    shutil.rmtree(root)
    return {"deleted": job_id}
