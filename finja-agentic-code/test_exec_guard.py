#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Container Write Boundary Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/exec_guard.py and for how the orchestrator
               uses it.

               "No direct writes into the running main container" is only
               worth anything if it fails closed when someone tries. These
               tests try: every container verb that writes, every flag that
               widens the worker, every way to smuggle a second mount, a
               flag given twice, a host folder that is not what it says.
               They also check, from the outside, that the pipeline really
               writes nowhere but its own jobs folder, and that no code path
               other than the two guarded call sites can start a process.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the guard itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import ast
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import exec_guard as guard  # noqa: E402
from core.exceptions import DirectWriteRefusedError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _path(*parts: str) -> str:
    """Build a POSIX path from parts, so no literal system path sits in this file."""
    return "/" + "/".join(parts)


BACKSLASH = chr(92)
DRIVE = "C" + ":"
HOST_DIR = _path("home", "fixture-account", "flare", "agent_jobs")
IMAGE = "finja-agent-worker:dev"
JOB = "ab12" * 8
OTHER_JOB = "cd34" * 8
PHASE = "preflight"
DOCKER_SOCKET = _path("var", "run", "docker.sock")


def good_run() -> list[str]:
    return guard.build_worker_run(JOB, PHASE, HOST_DIR, IMAGE)


def allowed(argv: list[str], **overrides: object) -> None:
    options: dict = {"host_jobs_dir": HOST_DIR, "worker_image": IMAGE}
    options.update(overrides)
    guard.require_allowed(argv, **options)


def refused(argv: object, **overrides: object) -> DirectWriteRefusedError:
    with pytest.raises(DirectWriteRefusedError) as excinfo:
        allowed(argv, **overrides)  # type: ignore[arg-type]
    return excinfo.value


# ==============================================================================
# The command Flare really runs
# ==============================================================================
class TestTheRealCommand:
    def test_the_builder_produces_exactly_the_command_flare_ran_before_the_guard(self) -> None:
        """Pins that adding the guard changed nothing about what a worker is given."""
        previous = [
            "docker", "run", "--rm", "--name", f"finja-agent-worker-{JOB[:12]}-{PHASE}",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", "--memory", "768m", "--cpus", "1",
            "-e", f"JOB_ID={JOB}", "-e", f"JOB_PHASE={PHASE}",
            "-v", f"{HOST_DIR}/{JOB}/sandbox:/jobs/{JOB}", IMAGE,
        ]
        assert good_run() == previous

    def test_the_real_command_is_allowed(self) -> None:
        allowed(good_run())
        allowed(tuple(good_run()))

    @pytest.mark.parametrize("phase", ["preflight", "test_patch", "apply_patch", "verify"])
    def test_every_phase_flare_has_is_allowed(self, phase: str) -> None:
        allowed(guard.build_worker_run(JOB, phase, HOST_DIR, IMAGE))

    def test_a_trailing_slash_on_the_host_folder_does_not_matter(self) -> None:
        assert guard.build_worker_run(JOB, PHASE, HOST_DIR + "/", IMAGE) == good_run()

    def test_a_host_folder_with_spaces_is_a_plain_path(self) -> None:
        folder = DRIVE + "/Users/Some One/agent jobs"
        argv = guard.build_worker_run(JOB, PHASE, folder, IMAGE)
        allowed(argv, host_jobs_dir=folder)
        assert f"{folder}/{JOB}/sandbox:/jobs/{JOB}" in argv

    def test_a_windows_style_folder_is_allowed(self) -> None:
        folder = DRIVE + BACKSLASH + "flare" + BACKSLASH + "agent_jobs"
        allowed(guard.build_worker_run(JOB, PHASE, folder, IMAGE), host_jobs_dir=folder)

    def test_the_removal_flare_issues_is_allowed(self) -> None:
        allowed(guard.build_worker_remove(guard.worker_container_name(JOB, PHASE)))


# ==============================================================================
# Verbs that write into a running container, and everything else
# ==============================================================================
class TestVerbs:
    @pytest.mark.parametrize("verb", [
        "exec", "cp", "commit", "attach", "start", "stop", "kill", "restart", "update", "create",
        "rename", "pause", "unpause", "import", "load", "build", "push", "pull", "network",
        "volume", "system", "compose", "container", "image", "", "RUN", "Run", "run;", "-H",
    ])
    def test_no_other_docker_verb_runs(self, verb: str) -> None:
        error = refused(["docker", verb, "finja-main", "sh", "-c", "echo changed > /app/main.py"])
        assert error.code == "FLARE-502"

    def test_a_refusal_names_the_verb_but_nothing_it_was_given(self) -> None:
        error = refused(["docker", "exec", "-it", "finja-main", "sh", "-c", "echo hunter2"])
        assert "exec" in str(error)
        assert "hunter2" not in str(error) and "finja-main" not in str(error)

    @pytest.mark.parametrize("program", [
        "sh", "bash", "/usr/bin/docker", "podman", "kubectl", "docker.exe", "nsenter", "ssh", "Docker",
    ])
    def test_only_the_docker_program_is_accepted(self, program: str) -> None:
        refused([program, *good_run()[1:]])

    @pytest.mark.parametrize("argv", [None, [], ["docker"], "docker run", 5, {"docker": "run"}])
    def test_malformed_commands_are_refused(self, argv: object) -> None:
        refused(argv)

    def test_non_text_tokens_are_refused(self) -> None:
        refused([*good_run(), 5])
        refused(["docker", 5])


# ==============================================================================
# `docker run`: everything that would widen the worker
# ==============================================================================
def _replace(argv: list[str], flag: str, value: str) -> list[str]:
    result = list(argv)
    result[result.index(flag) + 1] = value
    return result


def _drop(argv: list[str], flag: str, with_value: bool = True) -> list[str]:
    result = list(argv)
    index = result.index(flag)
    del result[index:index + (2 if with_value else 1)]
    return result


def _insert(argv: list[str], *extra: str) -> list[str]:
    return [*argv[:2], *extra, *argv[2:]]


def _without_env(argv: list[str], key: str) -> list[str]:
    result = list(argv)
    index = next(i for i, token in enumerate(result) if token.startswith(f"{key}="))
    del result[index - 1:index + 1]  # the "-e" and its value
    return result


def _v(target_mount: str) -> Callable[[list[str]], list[str]]:
    return lambda argv: _replace(argv, "-v", target_mount)


ATTACKS: dict[str, Callable[[list[str]], list[str]]] = {
    "privileged": lambda a: _insert(a, "--privileged"),
    "privileged-with-value": lambda a: _insert(a, "--privileged=true"),
    "pid-host": lambda a: _insert(a, "--pid", "host"),
    "pid-host-equals": lambda a: _insert(a, "--pid=host"),
    "ipc-host": lambda a: _insert(a, "--ipc", "host"),
    "uts-host": lambda a: _insert(a, "--uts", "host"),
    "userns-host": lambda a: _insert(a, "--userns", "host"),
    "network-host": lambda a: _replace(a, "--network", "host"),
    "network-bridge": lambda a: _replace(a, "--network", "bridge"),
    "network-container": lambda a: _replace(a, "--network", "container:finja-main"),
    "network-twice-host-last": lambda a: _insert(a, "--network", "host"),
    "network-twice-none-last": lambda a: [*a[:-1], "--network", "none", a[-1]],
    "cap-add": lambda a: _insert(a, "--cap-add", "SYS_ADMIN"),
    "cap-drop-weaker": lambda a: _replace(a, "--cap-drop", "NET_RAW"),
    "cap-drop-missing": lambda a: _drop(a, "--cap-drop"),
    "read-only-missing": lambda a: _drop(a, "--read-only", with_value=False),
    "no-new-privileges-missing": lambda a: _drop(a, "--security-opt"),
    "seccomp-unconfined": lambda a: _replace(a, "--security-opt", "seccomp=unconfined"),
    "apparmor-unconfined": lambda a: _insert(a, "--security-opt", "apparmor=unconfined"),
    "device": lambda a: _insert(a, "--device", _path("dev", "sda")),
    "volumes-from": lambda a: _insert(a, "--volumes-from", "finja-main"),
    "second-mount-socket": lambda a: _insert(a, "-v", f"{DOCKER_SOCKET}:{DOCKER_SOCKET}"),
    "second-mount-main-data": lambda a: _insert(a, "-v", f"{_path('srv', 'finja')}:/app"),
    "mount-flag": lambda a: _insert(a, "--mount", f"type=bind,source={_path('srv', 'finja')},target=/app"),
    "mount-root": _v(f"/:/jobs/{JOB}"),
    "mount-wrong-target": _v(f"{HOST_DIR}/{JOB}/sandbox:/app"),
    "mount-writable-etc": _v(f"{HOST_DIR}/{JOB}/sandbox:/" + "etc"),
    "mount-other-job": _v(f"{HOST_DIR}/{OTHER_JOB}/sandbox:/jobs/{JOB}"),
    "mount-workspace-not-sandbox": _v(f"{HOST_DIR}/{JOB}/workspace:/jobs/{JOB}"),
    "mount-request-snapshot": _v(f"{HOST_DIR}/{JOB}:/jobs/{JOB}"),
    "mount-option-injected": _v(f"{HOST_DIR}/{JOB}/sandbox:/jobs/{JOB}:rw,bind-propagation=shared"),
    "mount-parent-traversal": _v(f"{HOST_DIR}/../{JOB}/sandbox:/jobs/{JOB}"),
    "mount-other-host-folder": _v(f"{_path('srv', 'finja')}/{JOB}/sandbox:/jobs/{JOB}"),
    "mount-missing": lambda a: _drop(a, "-v"),
    "image-other": lambda a: [*a[:-1], "alpine:latest"],
    "image-main-app": lambda a: [*a[:-1], "finja-main:latest"],
    "image-missing": lambda a: a[:-1],
    "command-override": lambda a: [*a, "sh", "-c", "echo changed > /app/main.py"],
    "entrypoint": lambda a: _insert(a, "--entrypoint", "sh"),
    "user-root": lambda a: _insert(a, "--user", "0"),
    "name-main-container": lambda a: _replace(a, "--name", "finja-main"),
    "name-of-the-orchestrator": lambda a: _replace(a, "--name", "finja-agent-orchestrator"),
    "name-for-another-job": lambda a: _replace(a, "--name", f"finja-agent-worker-{OTHER_JOB[:12]}-{PHASE}"),
    "name-for-another-phase": lambda a: _replace(a, "--name", f"finja-agent-worker-{JOB[:12]}-verify"),
    "name-missing": lambda a: _drop(a, "--name"),
    "env-extra": lambda a: _insert(a, "-e", "SECRET=x"),
    "env-file": lambda a: _insert(a, "--env-file", "x.env"),
    "env-job-id-twice": lambda a: _insert(a, "-e", f"JOB_ID={OTHER_JOB}"),
    "env-job-id-other": lambda a: _replace(a, "-e", f"JOB_ID={OTHER_JOB}"),
    "env-without-equals": lambda a: _insert(a, "-e", "JOB_PHASE"),
    "env-job-id-malformed": lambda a: [("JOB_ID=../../x" if t == f"JOB_ID={JOB}" else t) for t in a],
    "pids-unlimited": lambda a: _replace(a, "--pids-limit", "-1"),
    "pids-zero": lambda a: _replace(a, "--pids-limit", "0"),
    "pids-huge": lambda a: _replace(a, "--pids-limit", "100000"),
    "pids-not-a-number": lambda a: _replace(a, "--pids-limit", "many"),
    "pids-missing": lambda a: _drop(a, "--pids-limit"),
    "memory-unlimited": lambda a: _replace(a, "--memory", "0"),
    "memory-malformed": lambda a: _replace(a, "--memory", "lots"),
    "memory-missing": lambda a: _drop(a, "--memory"),
    "cpus-malformed": lambda a: _replace(a, "--cpus", "all"),
    "tmpfs-root": lambda a: _replace(a, "--tmpfs", "/:rw"),
    "tmpfs-extra": lambda a: _insert(a, "--tmpfs", "/app:rw"),
    "tmpfs-missing": lambda a: _drop(a, "--tmpfs"),
    "rm-missing": lambda a: _drop(a, "--rm", with_value=False),
    "unknown-flag": lambda a: _insert(a, "--runtime", "runc"),
    "short-flag": lambda a: _insert(a, "-d"),
    "detached-tty": lambda a: _insert(a, "-it"),
    "publish-port": lambda a: _insert(a, "-p", "8080:8080"),
    "dns": lambda a: _insert(a, "--dns", "8.8.8.8"),
    "add-host": lambda a: _insert(a, "--add-host", "x:192.0.2.1"),
    "label": lambda a: _insert(a, "--label", "x=y"),
    "restart-policy": lambda a: _insert(a, "--restart", "always"),
    "flag-without-value-at-end": lambda a: [*a[:-1], "--memory"],
    "empty-token": lambda a: [*a, ""],
    "rm-twice": lambda a: _insert(a, "--rm"),
    "read-only-twice": lambda a: _insert(a, "--read-only"),
    "pids-twice-last-wins": lambda a: [*a[:-1], "--pids-limit", "100000", a[-1]],
    "memory-twice-last-wins": lambda a: [*a[:-1], "--memory", "9999g", a[-1]],
    "cpus-twice-last-wins": lambda a: [*a[:-1], "--cpus", "99", a[-1]],
    "tmpfs-twice-last-wins": lambda a: [*a[:-1], "--tmpfs", "/tmp:rw,size=9999g", a[-1]],
    "memory-zero-with-unit-is-unlimited": lambda a: _replace(a, "--memory", "0m"),
    "memory-zero-gigabytes": lambda a: _replace(a, "--memory", "0g"),
    "env-phase-missing": lambda a: _without_env(a, "JOB_PHASE"),
    "env-job-id-missing": lambda a: _without_env(a, "JOB_ID"),
}


class TestRunIsClosed:
    @pytest.mark.parametrize("name", sorted(ATTACKS))
    def test_widening_the_worker_is_refused(self, name: str) -> None:
        mutated = ATTACKS[name](good_run())
        assert mutated != good_run()
        error = refused(mutated)
        assert error.code == "FLARE-502"

    def test_the_attacks_start_from_an_allowed_command(self) -> None:
        """Otherwise every case above could be refused for the wrong reason."""
        allowed(good_run())

    def test_an_unconfigured_image_refuses_everything(self) -> None:
        refused(good_run(), worker_image="")

    def test_an_empty_image_is_not_an_image_even_when_the_command_agrees_with_it(self) -> None:
        argv = guard.build_worker_run(JOB, PHASE, HOST_DIR, "")
        refused(argv, worker_image="")

    def test_a_different_configured_image_refuses_the_default_one(self) -> None:
        refused(good_run(), worker_image="finja-agent-worker:other")

    def test_the_host_folder_the_command_was_built_for_must_match_the_configured_one(self) -> None:
        refused(good_run(), host_jobs_dir=_path("srv", "elsewhere"))


# ==============================================================================
# `docker rm`
# ==============================================================================
class TestRemove:
    NAME = f"finja-agent-worker-{JOB[:12]}-{PHASE}"

    def test_a_worker_container_can_be_force_removed(self) -> None:
        allowed(["docker", "rm", "-f", self.NAME])

    @pytest.mark.parametrize("target", [
        "finja-main", "finja-agent-orchestrator", "finja", "", "*", "-a", "$(docker ps -aq)",
        "finja-agent-worker-", "finja-agent-worker-abc-preflight", f"finja-agent-worker-{JOB[:12]}-",
        f"finja-agent-worker-{JOB[:12]}-Preflight", f"x-finja-agent-worker-{JOB[:12]}-{PHASE}",
        f"finja-agent-worker-{JOB[:12]}-{PHASE} finja-main", f"finja-agent-worker-{JOB[:12]}-{PHASE}\n",
        f"finja-agent-worker-{JOB[:12]}-{PHASE};id",
    ])
    def test_nothing_but_a_worker_container_can_be_removed(self, target: str) -> None:
        refused(["docker", "rm", "-f", target])

    @pytest.mark.parametrize("argv", [
        ["docker", "rm", NAME],
        ["docker", "rm"],
        ["docker", "rm", "-f"],
        ["docker", "rm", "-f", NAME, "finja-main"],
        ["docker", "rm", "-fv", NAME],
        ["docker", "rm", "-v", "-f", NAME],
        ["docker", "rm", "--volumes", "-f", NAME],
        ["docker", "rm", NAME, "-f"],
        ["docker", "rm", "--force", NAME],
        ["docker", "container", "rm", "-f", NAME],
        ["docker", "rmi", "-f", IMAGE],
    ])
    def test_only_the_exact_forced_removal_shape_is_accepted(self, argv: list[str]) -> None:
        refused(argv)

    def test_the_builder_refuses_what_the_guard_would(self) -> None:
        with pytest.raises(DirectWriteRefusedError):
            guard.build_worker_remove("finja-main")
        with pytest.raises(DirectWriteRefusedError):
            guard.build_worker_remove("")


# ==============================================================================
# The host folder
# ==============================================================================
class TestHostFolder:
    @pytest.mark.parametrize("folder", [
        HOST_DIR, HOST_DIR + "/", _path("srv", "flare", "jobs"), _path("opt", "x"),
        DRIVE + "/flare/jobs", DRIVE.lower() + "/flare/jobs/", DRIVE + BACKSLASH + "flare" + BACKSLASH + "jobs",
        _path("var", "lib", "flare"), _path("mnt", "data", "my jobs (old)"), _path("usr", "local", "flare"),
    ])
    def test_ordinary_folders_are_accepted(self, folder: str) -> None:
        guard.validate_host_jobs_dir(folder)

    @pytest.mark.parametrize("folder", [
        None, "", "   ", "relative/path", "jobs", ".", "..", "./jobs", "~/jobs",
        "/", "//", DRIVE + "/", DRIVE + BACKSLASH,
        _path("srv", "jobs") + ":/" + "etc" + ":rw",
        _path("srv", "jobs:ro"),
        _path("srv", "..", "jobs"), _path("srv", ".", "jobs"), _path("srv", "jobs", ".."),
        _path("srv", "jobs") + "\n" + _path("srv", "other"),
        _path("srv", "jobs") + "\x00",
        _path("srv", "jobs;rm"), _path("srv", "$(id)"), _path("srv", "jobs`x`"), _path("srv", "a|b"),
        _path("srv", "a&b"), _path("srv", "a>b"), _path("srv", 'a"b'), _path("srv", "a'b"),
        _path("srv", "a*"), _path("srv", "a?"),
        DOCKER_SOCKET, _path("var", "run"), _path("var", "run", "x"), _path("run", "x"),
        _path("etc"), _path("etc", "flare"), _path("proc", "1"), _path("sys", "x"), _path("dev", "x"),
        _path("boot"), _path("root"), _path("root", "jobs"), _path("bin"), _path("sbin", "x"),
        _path("srv", "docker.sock"), DRIVE + "/ProgramData/docker.sock",
        _path("ETC", "x"),
        "ftp://host/jobs", "http://host/jobs", "C:jobs",
    ])
    def test_folders_that_are_not_a_plain_place_for_jobs_are_refused(self, folder: object) -> None:
        with pytest.raises(DirectWriteRefusedError):
            guard.validate_host_jobs_dir(folder)  # type: ignore[arg-type]

    def test_a_colon_cannot_add_mount_options_even_though_it_passes_other_checks(self) -> None:
        with pytest.raises(DirectWriteRefusedError):
            guard.validate_host_jobs_dir(HOST_DIR + ":ro")

    @pytest.mark.parametrize("folder", [
        _path("srv", "finja"), _path("srv", "finja") + "/", _path("srv", "finja", "data"),
        _path("srv", "finja", "data", "deep", "er"), _path("SRV", "Finja", "data"),
        BACKSLASH.join(["C:", "finja", "data"]),
    ])
    def test_a_protected_host_path_and_everything_under_it_is_refused(self, folder: str) -> None:
        protected = [_path("srv", "finja"), DRIVE + "/finja"]
        with pytest.raises(DirectWriteRefusedError):
            guard.validate_host_jobs_dir(folder, protected)

    @pytest.mark.parametrize("folder", [
        _path("srv", "finja2"), _path("srv", "fin"), _path("srv"), _path("srv", "flare", "finja"),
        DRIVE + "/finja2",
    ])
    def test_a_sibling_or_parent_of_a_protected_path_is_not_inside_it(self, folder: str) -> None:
        guard.validate_host_jobs_dir(folder, [_path("srv", "finja"), DRIVE + "/finja"])

    def test_protected_paths_also_apply_to_the_whole_command(self) -> None:
        refused(good_run(), protected_paths=[_path("home", "fixture-account")])
        allowed(good_run(), protected_paths=[_path("home", "someone-else")])

    def test_parsing_the_protected_path_setting(self) -> None:
        assert guard.parse_protected_paths("") == ()
        assert guard.parse_protected_paths(None) == ()  # type: ignore[arg-type]
        assert guard.parse_protected_paths(" /a , ,/b,") == ("/a", "/b")

    def test_builder_names_refuse_bad_ids_and_phases(self) -> None:
        for job_id, phase in [("", PHASE), ("x" * 32, PHASE), (JOB, ""), (JOB, "Pre"), (JOB, "a" * 40),
                              (JOB.upper(), PHASE), (JOB + "0", PHASE), (JOB, "a-b"), (JOB, "../x")]:
            with pytest.raises(DirectWriteRefusedError):
                guard.worker_container_name(job_id, phase)


# ==============================================================================
# The orchestrator uses it
# ==============================================================================
class _Process:
    returncode = 125

    def poll(self) -> int | None:
        return None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return "", "stopped by the test\n"

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        pass


@pytest.fixture
def pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "Pipeline":
    monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
    monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(main, "HOST_JOBS_DIR", HOST_DIR)
    monkeypatch.setattr(main, "WORKER_IMAGE", IMAGE)
    monkeypatch.setattr(main, "PROTECTED_HOST_PATHS", ())
    return Pipeline(monkeypatch)


class Pipeline:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.started: list[list[str]] = []
        self.ran: list[list[str]] = []
        monkeypatch.setattr(main.subprocess, "Popen", self._popen)
        monkeypatch.setattr(main.subprocess, "run", self._run)

    def _popen(self, cmd: list[str], **kwargs: object) -> _Process:
        self.started.append(list(cmd))
        return _Process()

    def _run(self, cmd: list[str], **kwargs: object) -> object:
        self.ran.append(list(cmd))
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    @staticmethod
    def job() -> str:
        return main.stage_job(main.CreateJobRequest(
            task="Fix it", files=[main.JobFile(path="demo.py", content="x = 1\n")]))


class TestOrchestratorWiring:
    def test_the_worker_phase_runs_the_guarded_command_and_nothing_else(self, pipeline: Pipeline) -> None:
        job_id = pipeline.job()
        with pytest.raises(main.WorkerExecutionError):
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        assert pipeline.started == [guard.build_worker_run(job_id, "preflight", HOST_DIR, IMAGE)]
        assert pipeline.ran == [["docker", "rm", "-f", f"finja-agent-worker-{job_id[:12]}-preflight"]]

    def test_every_command_that_reaches_the_process_layer_passes_the_guard(self, pipeline: Pipeline) -> None:
        job_id = pipeline.job()
        with pytest.raises(main.WorkerExecutionError):
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)
        for argv in [*pipeline.started, *pipeline.ran]:
            guard.require_allowed(argv, host_jobs_dir=HOST_DIR, worker_image=IMAGE)

    def test_the_guard_is_really_in_the_path(self, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
        def veto(argv: list[str], **kwargs: object) -> None:
            raise DirectWriteRefusedError("vetoed by the test")

        monkeypatch.setattr(main.exec_guard, "require_allowed", veto)
        job_id = pipeline.job()
        with pytest.raises(DirectWriteRefusedError):
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)
        assert pipeline.started == []

    @pytest.mark.parametrize("folder", [
        _path("etc"), DOCKER_SOCKET, "/", HOST_DIR + ":" + _path("etc") + ":rw", "relative",
    ])
    def test_a_misconfigured_host_folder_stops_the_job_before_docker_is_asked(
        self, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch, folder: str
    ) -> None:
        monkeypatch.setattr(main, "HOST_JOBS_DIR", folder)
        job_id = pipeline.job()
        with pytest.raises(DirectWriteRefusedError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)
        assert excinfo.value.code == "FLARE-502"
        assert pipeline.started == []

    def test_a_protected_path_stops_the_job_before_docker_is_asked(
        self, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "PROTECTED_HOST_PATHS", (_path("home", "fixture-account"),))
        job_id = pipeline.job()
        with pytest.raises(DirectWriteRefusedError):
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)
        assert pipeline.started == []

    def test_a_removal_aimed_at_anything_but_a_worker_is_not_carried_out(
        self, pipeline: Pipeline, caplog: pytest.LogCaptureFixture
    ) -> None:
        main._force_remove_worker_container("finja-main")
        main._force_remove_worker_container("finja-agent-orchestrator")
        assert pipeline.ran == []
        assert "FLARE-502" in caplog.text

    def test_a_removal_of_a_worker_is_carried_out(self, pipeline: Pipeline) -> None:
        name = f"finja-agent-worker-{JOB[:12]}-verify"
        main._force_remove_worker_container(name)
        assert pipeline.ran == [["docker", "rm", "-f", name]]

    def test_cancel_still_finishes_when_the_removal_is_refused(self, pipeline: Pipeline) -> None:
        main._stop_worker_process(_Process(), "finja-main")  # must not raise
        assert pipeline.ran == []

    def test_health_reports_the_boundary(self, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(main.app)
        block = client.get("/health").json()["write_boundary"]
        assert block == {"container_commands_allowed": ["run", "rm"], "host_jobs_dir_ok": True,
                         "protected_host_paths": 0}
        monkeypatch.setattr(main, "HOST_JOBS_DIR", _path("etc"))
        monkeypatch.setattr(main, "PROTECTED_HOST_PATHS", ("/a", "/b"))
        block = client.get("/health").json()["write_boundary"]
        assert block["host_jobs_dir_ok"] is False and block["protected_host_paths"] == 2

    def test_health_says_not_ok_when_the_folder_is_unset(self, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "HOST_JOBS_DIR", "")
        assert TestClient(main.app).get("/health").json()["write_boundary"]["host_jobs_dir_ok"] is False


# ==============================================================================
# Seen from the outside: where does the pipeline write?
# ==============================================================================
_WRITE_EVENTS = frozenset({
    "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.truncate", "os.chmod", "os.symlink", "os.link",
    "shutil.copyfile", "shutil.copytree", "shutil.rmtree", "shutil.move",
})
_RECORDER = {"thread": None, "paths": []}


def _audit(event: str, args: tuple) -> None:
    if _RECORDER["thread"] != threading.get_ident():
        return
    if event == "open":
        _path_arg, _mode, flags = args
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC):
            if isinstance(_path_arg, (str, bytes, os.PathLike)):
                _RECORDER["paths"].append(os.fsdecode(_path_arg))
    elif event in _WRITE_EVENTS:
        for item in args:
            if isinstance(item, (str, bytes, os.PathLike)):
                _RECORDER["paths"].append(os.fsdecode(item))
                break


sys.addaudithook(_audit)


class _Recording:
    def __enter__(self) -> list[str]:
        _RECORDER["paths"] = []
        _RECORDER["thread"] = threading.get_ident()
        return _RECORDER["paths"]

    def __exit__(self, *exc: object) -> None:
        _RECORDER["thread"] = None


class TestWritesStayInTheJobsFolder:
    def test_the_recorder_sees_a_write_outside(self, tmp_path: Path) -> None:
        """Otherwise the test below could pass because the recorder is blind."""
        with _Recording() as paths:
            (tmp_path / "elsewhere.txt").write_text("x")
            (tmp_path / "dir").mkdir()
        assert any(p.endswith("elsewhere.txt") for p in paths)
        assert any(p.endswith("dir") for p in paths)

    def test_a_whole_job_life_writes_only_under_the_jobs_folder(
        self, pipeline: Pipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = tmp_path / "main_container_tree"
        outside.mkdir()
        sentinel = outside / "app.py"
        sentinel.write_text("pass  # stands in for the main container's code\n")
        before = sentinel.read_bytes()
        jobs_root = os.path.realpath(main.JOBS_DIR)

        with _Recording() as paths:
            job_id = pipeline.job()
            main.write_status(job_id, "analysing")
            with pytest.raises(main.WorkerExecutionError):
                main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)
            main.write_status(job_id, "patching")
            main.write_status(job_id, "testing")
            main.write_status(job_id, "awaiting_approval", result={"files": []}, approval_required=True)
            main.supervisor_sweep()
            main._roll_back_job(job_id, "the test is done")

        assert len(paths) > 20, "the recorder must have seen the pipeline work"
        escaped = sorted({p for p in paths if not os.path.realpath(p).startswith(jobs_root)})
        assert escaped == []
        assert sentinel.read_bytes() == before
        assert sorted(p.name for p in outside.iterdir()) == ["app.py"]


# ==============================================================================
# Seen from the source: is there any other way to start a process?
# ==============================================================================
_PROCESS_CALLS = {
    "subprocess": {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"},
    "os": {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe",
           "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
           "posix_spawn", "posix_spawnp", "startfile", "fork", "forkpty"},
    "pty": {"spawn"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
}
_GUARDED_FUNCTIONS = {"_force_remove_worker_container", "run_worker_phase"}
_FORBIDDEN_IMPORTS = {"docker", "pty", "paramiko", "fabric", "pexpect", "kubernetes", "podman", "plumbum", "sh"}


def _python_sources(*folders: str) -> list[Path]:
    files: list[Path] = []
    for folder in folders:
        files.extend(sorted((_MODULE_ROOT / folder).glob("*.py")))
    return files


def _process_call_sites(path: Path) -> list[tuple[str, str]]:
    """(enclosing function, dotted call) for every call that can start a process."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                owner = child.func.value
                if isinstance(owner, ast.Name) and child.func.attr in _PROCESS_CALLS.get(owner.id, ()):
                    found.append((scope, f"{owner.id}.{child.func.attr}"))
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id in {"__import__", "exec", "eval", "system"}:
                    found.append((scope, child.func.id))
            visit(child, inner)

    visit(tree, "<module>")
    return found


class TestNoOtherWayToStartAProcess:
    def test_the_orchestrator_starts_processes_in_exactly_two_guarded_places(self) -> None:
        sites = _process_call_sites(_MODULE_ROOT / "orchestrator" / "app" / "main.py")
        assert {scope for scope, _call in sites} == _GUARDED_FUNCTIONS
        assert sorted(call for _scope, call in sites) == ["subprocess.Popen", "subprocess.run"]

    def test_the_core_package_and_the_other_app_modules_start_none(self) -> None:
        offenders = {}
        for path in _python_sources("core", "orchestrator/app"):
            if path.name == "main.py":
                continue
            sites = _process_call_sites(path)
            if sites:
                offenders[path.name] = sites
        assert offenders == {}

    @pytest.mark.parametrize("function", sorted(_GUARDED_FUNCTIONS))
    def test_each_guarded_place_asks_the_guard_before_it_runs_anything(self, function: str) -> None:
        source = (_MODULE_ROOT / "orchestrator" / "app" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
        asked = [c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Attribute) and c.func.attr == "require_allowed"]
        runs = [c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute) and c.func.attr in {"Popen", "run"}
                and isinstance(c.func.value, ast.Name) and c.func.value.id == "subprocess"]
        assert asked and runs and min(asked) < min(runs)

    def test_no_command_is_assembled_by_hand_next_to_a_call(self) -> None:
        """The argument of both calls is the guarded value, not a literal or an expression."""
        tree = ast.parse((_MODULE_ROOT / "orchestrator" / "app" / "main.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
                    and node.func.attr in {"Popen", "run"}):
                assert isinstance(node.args[0], ast.Name) and node.args[0].id in {"argv", "cmd"}

    def test_no_module_imports_a_docker_or_remote_execution_library(self) -> None:
        offenders = []
        for path in _python_sources("core", "orchestrator/app"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                offenders += [(path.name, n) for n in names if n in _FORBIDDEN_IMPORTS]
        assert offenders == []

    def test_nothing_talks_to_the_docker_socket_directly(self) -> None:
        pattern = re.compile(r"docker\.sock|unix://|AF_UNIX|/var/run/docker", re.IGNORECASE)
        offenders = []
        for path in _python_sources("core", "orchestrator/app"):
            if path.name == "exec_guard.py":
                continue  # names the socket only to refuse it
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append((path.name, number))
        assert offenders == []

    def test_the_rest_of_the_repository_has_no_container_write_command(self) -> None:
        """Scripts, compose files and Dockerfiles: no exec/cp/commit into a running container."""
        pattern = re.compile(
            r"\bdocker(?:-compose|\s+compose)?\s+(?:container\s+)?(?:exec|cp|commit|attach)\b"
            r"|\bkubectl\s+(?:exec|cp|patch|edit|replace)\b|--privileged|--volumes-from|--pid[= ]host"
        )
        skipped_dirs = {"private", ".git", "__pycache__", "node_modules", ".pytest_cache", "contracts"}
        offenders = []
        for path in sorted(_MODULE_ROOT.rglob("*")):
            relative = path.relative_to(_MODULE_ROOT)
            if skipped_dirs & set(relative.parts) or not path.is_file():
                continue
            if path.suffix not in {".py", ".sh", ".yml", ".yaml", ".ps1", ".bat", ".cmd", ""} and path.name != "Dockerfile":
                continue
            if path.name.startswith("test_") or path.name == "exec_guard.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pattern.search(line):
                    offenders.append((str(relative), number))
        assert offenders == []

    @pytest.mark.parametrize("compose", ["docker-compose.yml", "docker-compose.testbed.yml"])
    def test_compose_mounts_only_the_jobs_folder_and_the_socket_and_asks_for_no_host_access(
        self, compose: str
    ) -> None:
        text = (_MODULE_ROOT / compose).read_text(encoding="utf-8")
        active = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        mounts = [line.split("-", 1)[1].strip() for line in active
                  if re.match(r"^\s+- .*:/.*", line) and "ports" not in line]
        mounts = [m for m in mounts if not re.match(r"^[\"']?\$?\{?[A-Z_]*:?-?[0-9.]*[\"']?:?\d+:\d+", m)]
        allowed_targets = {"/jobs", DOCKER_SOCKET}
        targets = {m.rsplit(":", 1)[-1].strip("\"'") for m in mounts if "/" in m.rsplit(":", 1)[-1]}
        assert targets <= allowed_targets, targets
        forbidden = re.compile(r"^\s*(privileged:\s*true|pid:\s*host|network_mode:\s*host|volumes_from:|ipc:\s*host)",
                               re.MULTILINE)
        assert forbidden.search("\n".join(active)) is None
        socket_services = [m for m in mounts if "docker.sock" in m]
        assert len(socket_services) == 1
