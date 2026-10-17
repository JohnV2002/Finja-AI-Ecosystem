"""
======================================================================
      Flare (Finja Agentic Code) – Container Write Boundary
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: The one place that decides which container commands Flare
               may run. Pure: it builds and judges argument lists; the
               orchestrator runs what passes.

  New in v1.11.0:
    - First version: "no direct writes into a running main container"
      stops being a convention and becomes something that fails closed.

----------------------------------------------------------------------

  The situation, measured. Flare's pipeline writes 65 paths for one
  job's life (stage, worker phase, approval, supervisor sweep, rollback),
  and every one is under JOBS_DIR. Nothing it does reaches another
  container. But that was true by construction only: the orchestrator holds
  the Docker socket, which can `exec` into, `cp` into or `commit` any
  container on the host, and the only thing keeping Flare from doing so was
  that nobody had written such a line. A later change, a refactor that
  builds the command from a variable, or a model-influenced value that
  reaches a command line would not have been stopped by anything.

  So the commands are now data that is judged before it is run:

    * Only two shapes exist. `docker run` of the worker image, with the
      hardening Flare already used (offline, read-only, no capabilities,
      no new privileges, bounded) and exactly one bind mount: this job's
      own sandbox copy. And `docker rm -f` of a worker container, by a
      name that only a worker can have.
    * Anything else is refused: `exec`, `cp`, `commit`, `start`, `stop`,
      `kill`, `restart`, `update`, `attach`, `create`, any other image,
      any other mount, the Docker socket, `--privileged`, host networking
      or PID namespaces, extra capabilities, a command override.
    * A flag given twice is refused: with `--network none --network host`
      the last one wins, and "the guard saw `none`" would be no comfort.
    * The configured host folder is judged too. A mount source built from a
      misconfigured AGENT_JOBS_HOST_DIR could make Docker create folders in
      a place that was never meant for Flare, or smuggle mount options in
      after a colon. An operator can also list protected host paths (the
      main container's data) that no mount may sit in.

  What this is not: it cannot stop someone who already has a shell in the
  orchestrator container or code execution in its process, because with the
  Docker socket that is the host. That boundary belongs to the deployment
  (see the README); this module closes the gap inside Flare's own code.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from core.exceptions import DirectWriteRefusedError

ALLOWED_VERBS = ("run", "rm")

WORKER_NAME_PREFIX = "finja-agent-worker-"
WORKER_NAME_RE = re.compile(r"^finja-agent-worker-[0-9a-f]{12}-[a-z][a-z_]{0,23}$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PHASE_RE = re.compile(r"^[a-z][a-z_]{0,23}$")

SANDBOX_MOUNT_TARGET = "/jobs"
TMPFS_TARGET = "/tmp"  # noqa: S108 - the container's own tmpfs, not a host path

DEFAULT_MEMORY = "768m"
DEFAULT_CPUS = "1"
DEFAULT_PIDS = 64
MAX_PIDS = 256

_MEMORY_RE = re.compile(r"^[1-9][0-9]{0,4}[mg]$")
_CPUS_RE = re.compile(r"^[1-9][0-9]?(\.[0-9]{1,2})?$")
_TMPFS_RE = re.compile(r"^/tmp:[a-z0-9=,]{1,64}$")  # noqa: S108
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_HOST_DIR_FORBIDDEN_RE = re.compile(r"[\x00-\x1f\x7f\"'`$;|&<>*?!^{}\[\]]")

# Host trees a bind mount must never be rooted in.
_SYSTEM_TREES = ("/etc", "/proc", "/sys", "/dev", "/run", "/var/run", "/boot", "/root", "/bin", "/sbin")

_FLAGS_WITHOUT_VALUE = frozenset({"--rm", "--read-only"})
_FLAGS_WITH_VALUE = frozenset({
    "--name", "--network", "--cap-drop", "--security-opt", "--pids-limit",
    "--tmpfs", "--memory", "--cpus", "-e", "-v",
})
_REQUIRED_FLAGS = _FLAGS_WITHOUT_VALUE | _FLAGS_WITH_VALUE


def _refuse(reason: str, **context: object) -> DirectWriteRefusedError:
    return DirectWriteRefusedError(
        f"Refused to run a container command outside the worker allowlist: {reason}",
        reason=reason, **context,
    )


def _short(value: object) -> str:
    text = str(value)
    cleaned = re.sub(r"[^A-Za-z0-9_.=:/-]", "?", text)
    return cleaned[:40]


def _normalise(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").lower()


def validate_host_jobs_dir(value: str, protected_paths: Iterable[str] = ()) -> str:
    """
    Return the host jobs folder in the form it is mounted from, or refuse.

    The value ends up inside a `-v source:target` argument, so anything that
    could be read as an option separator, a second mount or a shell construct
    is refused, as are system trees, the Docker socket and every folder an
    operator has declared protected (the main container's data).
    """
    if not isinstance(value, str) or not value.strip():
        raise _refuse("the host jobs folder is not configured")
    if _HOST_DIR_FORBIDDEN_RE.search(value):
        raise _refuse("the host jobs folder contains characters that are not part of a plain path")
    if not (value.startswith("/") or _DRIVE_RE.match(value)):
        raise _refuse("the host jobs folder is not an absolute path")
    if ":" in value[2:] or (":" in value[:2] and not _DRIVE_RE.match(value)):
        raise _refuse("the host jobs folder contains a colon, which would add mount options")
    segments = [part for part in re.split(r"[\\/]+", value) if part]
    if ".." in segments or "." in segments:
        raise _refuse("the host jobs folder contains relative segments")
    cleaned = value.rstrip("/\\")
    flat = _normalise(cleaned)
    if flat in {"", "/"} or re.fullmatch(r"[a-z]:", flat):
        raise _refuse("the host jobs folder is a filesystem root")
    if "docker.sock" in flat:
        raise _refuse("the host jobs folder names the Docker socket")
    for tree in _SYSTEM_TREES:
        if flat == tree or flat.startswith(tree + "/"):
            raise _refuse("the host jobs folder is inside a system tree")
    for protected in protected_paths:
        guarded = _normalise(str(protected))
        if guarded and (flat == guarded or flat.startswith(guarded + "/")):
            raise _refuse("the host jobs folder is inside a protected host path")
    return cleaned


def worker_container_name(job_id: str, phase: str) -> str:
    if not JOB_ID_RE.fullmatch(job_id or ""):
        raise _refuse("the job id is not a job id")
    if not PHASE_RE.fullmatch(phase or ""):
        raise _refuse("the phase name is not a phase name")
    return f"{WORKER_NAME_PREFIX}{job_id[:12]}-{phase}"


def build_worker_run(job_id: str, phase: str, host_jobs_dir: str, image: str) -> list[str]:
    """The only `docker run` Flare issues. Mounts this job's sandbox copy and nothing else."""
    source_root = validate_host_jobs_dir(host_jobs_dir)
    name = worker_container_name(job_id, phase)
    return [
        "docker", "run", "--rm",
        "--name", name,
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(DEFAULT_PIDS),
        "--tmpfs", f"{TMPFS_TARGET}:rw,nosuid,nodev,size=64m",
        "--memory", DEFAULT_MEMORY,
        "--cpus", DEFAULT_CPUS,
        "-e", f"JOB_ID={job_id}",
        "-e", f"JOB_PHASE={phase}",
        "-v", f"{source_root}/{job_id}/sandbox:{SANDBOX_MOUNT_TARGET}/{job_id}",
        image,
    ]


def build_worker_remove(container_name: str) -> list[str]:
    """The only `docker rm` Flare issues: forced removal of a worker container."""
    if not WORKER_NAME_RE.fullmatch(container_name or ""):
        raise _refuse("the container to remove is not a worker container", name=_short(container_name))
    return ["docker", "rm", "-f", container_name]


def _split_flags(tokens: Sequence[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Parse flags strictly. Unknown flags, `--flag=value` forms and repeats are refusals."""
    seen: dict[str, list[str]] = {}
    positional: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not isinstance(token, str):
            raise _refuse("an argument is not text")
        if token.startswith("-"):
            if token in _FLAGS_WITHOUT_VALUE:
                if token in seen:
                    raise _refuse(f"flag {token} is given twice")
                seen[token] = []
                index += 1
                continue
            if token in _FLAGS_WITH_VALUE:
                if index + 1 >= len(tokens):
                    raise _refuse(f"flag {token} has no value")
                values = seen.setdefault(token, [])
                if token != "-e" and values:
                    raise _refuse(f"flag {token} is given twice")
                values.append(tokens[index + 1])
                index += 2
                continue
            raise _refuse(f"flag {_short(token)} is not allowed")
        positional.append(token)
        index += 1
    return seen, positional


def _check_run(tokens: Sequence[str], host_jobs_dir: str, worker_image: str, protected: Iterable[str]) -> None:
    flags, positional = _split_flags(tokens)
    missing = sorted(flag for flag in _REQUIRED_FLAGS if flag not in flags)
    if missing:
        raise _refuse(f"required flag {missing[0]} is missing")

    if flags["--network"] != ["none"]:
        raise _refuse("the worker must run without a network")
    if flags["--cap-drop"] != ["ALL"]:
        raise _refuse("the worker must drop all capabilities")
    if flags["--security-opt"] != ["no-new-privileges"]:
        raise _refuse("the worker must run with no-new-privileges")
    pids = flags["--pids-limit"][0]
    if not pids.isdigit() or not 1 <= int(pids) <= MAX_PIDS:
        raise _refuse("the pids limit is out of range")
    if not _MEMORY_RE.fullmatch(flags["--memory"][0]):
        raise _refuse("the memory limit is malformed")
    if not _CPUS_RE.fullmatch(flags["--cpus"][0]):
        raise _refuse("the cpu limit is malformed")
    if not _TMPFS_RE.fullmatch(flags["--tmpfs"][0]):
        raise _refuse("the only tmpfs allowed is the worker's own /tmp")

    environment: dict[str, str] = {}
    for item in flags["-e"]:
        key, separator, value = item.partition("=")
        if not separator or key in environment:
            raise _refuse("only JOB_ID and JOB_PHASE may be set, once each")
        environment[key] = value
    if set(environment) != {"JOB_ID", "JOB_PHASE"}:
        raise _refuse("JOB_ID and JOB_PHASE must both be set")
    job_id, phase = environment["JOB_ID"], environment["JOB_PHASE"]

    # worker_container_name refuses a malformed id or phase, so this one
    # comparison also pins what the environment may say.
    if flags["--name"] != [worker_container_name(job_id, phase)]:
        raise _refuse("the container name does not belong to this job and phase")

    source_root = validate_host_jobs_dir(host_jobs_dir, protected)
    expected_mount = f"{source_root}/{job_id}/sandbox:{SANDBOX_MOUNT_TARGET}/{job_id}"
    if flags["-v"] != [expected_mount]:
        raise _refuse("the only mount allowed is this job's own sandbox copy")

    if positional != [worker_image]:
        raise _refuse("only the worker image may run, with its own entrypoint")


def _check_remove(tokens: Sequence[str]) -> None:
    if len(tokens) != 2 or tokens[0] != "-f":
        raise _refuse("docker rm is only allowed as a forced removal of one container")
    if not WORKER_NAME_RE.fullmatch(tokens[1]):
        raise _refuse("the container to remove is not a worker container", name=_short(tokens[1]))


def require_allowed(
    argv: Sequence[str],
    *,
    host_jobs_dir: str = "",
    worker_image: str = "",
    protected_paths: Iterable[str] = (),
) -> None:
    """Raise DirectWriteRefusedError unless `argv` is exactly an allowed worker command."""
    if not isinstance(argv, (list, tuple)) or len(argv) < 2:
        raise _refuse("the command is empty")
    if argv[0] != "docker":
        raise _refuse(f"program {_short(argv[0])} is not docker")
    verb = argv[1]
    if verb not in ALLOWED_VERBS:
        raise _refuse(f"docker {_short(verb)} is not allowed; Flare never writes to a running container",
                      verb=_short(verb))
    if verb == "rm":
        _check_remove(argv[2:])
        return
    if not worker_image:
        raise _refuse("no worker image is configured")
    _check_run(argv[2:], host_jobs_dir, worker_image, protected_paths)


def parse_protected_paths(raw: str) -> tuple[str, ...]:
    """`FLARE_PROTECTED_HOST_PATHS`: comma separated host paths no worker mount may sit in."""
    return tuple(part.strip() for part in (raw or "").split(",") if part.strip())
