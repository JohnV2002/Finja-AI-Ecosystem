"""
Project: Finja - Twitch Interactivity Suite
Module: finja-cloud-memory / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 4.5.0
Description: Key rotation of the memory files, the protection against overwriting unreadable
    files, the owner-only probe and structured reports. Lives next to the code (not in tests/)
    because it needs pytest and FastAPI, which Flare's unittest sandbox does not have.
New in 4.5.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
OLD_KEY = "old-key-that-leaked"
NEW_KEY = "brand-new-key-for-memories"
TOKEN = "probe-" + "p" * 16

import encrypt_memory_at_rest as rotate  # noqa: E402
from analytics_sender import AnalyticsConfig, AnalyticsSender  # noqa: E402
from core.exceptions import MemoryDiagnosticsProbeError, MemoryNotConfiguredError, MemoryStorageError  # noqa: E402


def _load_server(env: dict):
    with patch.dict("os.environ", env, clear=False):
        spec = importlib.util.spec_from_file_location("memory_server_flare", ROOT / "memory-server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


@pytest.fixture()
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINJA_DATA_ENCRYPTION_KEY", NEW_KEY)
    module = _load_server({"MEMORY_API_KEY": "test-api-key", "FINJA_DATA_ENCRYPTION_KEY": NEW_KEY})
    monkeypatch.setattr(module, "USER_MEMORY_DIR", str(tmp_path))
    reported: list = []
    monkeypatch.setattr(module.analytics, "record_exception", lambda error: reported.append(error))
    module.user_memories.clear()
    module._load_failed.clear()
    module._last_reported.clear()
    return module, reported


def test_missing_api_key_is_finja_107(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORY_API_KEY", raising=False)
    with patch.object(Path, "exists", return_value=False):  # no private/.env in this test
        with pytest.raises(MemoryNotConfiguredError) as caught:
            _load_server({"MEMORY_API_KEY": ""})
    assert caught.value.code == "FINJA-107"


def test_an_unreadable_file_is_never_overwritten(server) -> None:
    module, reported = server
    path = Path(module.memory_file("alice"))
    path.write_bytes(rotate.encrypt(json.dumps([{"text": "secret", "timestamp": 1.0}]).encode(), rotate.key_bytes(OLD_KEY)))
    before = path.read_bytes()
    module.load_from_disk("alice")
    module.user_memories["alice"] = []
    module.save_to_disk("alice")
    assert path.read_bytes() == before
    assert "alice" in module._load_failed
    assert reported and all(isinstance(e, MemoryStorageError) for e in reported)


def test_a_readable_file_loads_and_saves_again(server) -> None:
    module, _ = server
    path = Path(module.memory_file("bob"))
    path.write_bytes(rotate.encrypt(json.dumps([{"text": "hi", "timestamp": 2.0}]).encode(), rotate.key_bytes(NEW_KEY)))
    module.load_from_disk("bob")
    assert [m.text for m in module.user_memories["bob"]] == ["hi"] and "bob" not in module._load_failed
    module.save_to_disk("bob")
    assert json.loads(module.decrypt_bytes(path.read_bytes()))[0]["text"] == "hi"


@pytest.fixture()
def rotation_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "user_memories").mkdir()
    (tmp_path / "backups" / "2026").mkdir(parents=True)
    monkeypatch.setattr(rotate, "BASE_DIR", tmp_path)
    monkeypatch.setattr(rotate, "USER_MEMORY_DIR", tmp_path / "user_memories")
    monkeypatch.setattr(rotate, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setenv("FINJA_DATA_ENCRYPTION_KEY", NEW_KEY)
    monkeypatch.setenv("FINJA_DATA_ENCRYPTION_KEY_OLD", OLD_KEY)
    return tmp_path


def test_rotation_rekeys_memories_and_backups_for_the_server(rotation_dirs: Path, server) -> None:
    module, _ = server
    data = json.dumps([{"text": "remember me", "timestamp": 3.0}]).encode()
    old = rotate.key_bytes(OLD_KEY)
    (rotation_dirs / "user_memories" / "alice_memory.json").write_bytes(rotate.encrypt(data, old))
    (rotation_dirs / "user_memories" / "plain_memory.json").write_bytes(data)
    (rotation_dirs / "backups" / "2026" / "alice_memory.json").write_bytes(rotate.encrypt(data, old))

    assert rotate.main(["--check", "--include-backups"]) == 0
    assert (rotation_dirs / "user_memories" / "plain_memory.json").read_bytes() == data  # check writes nothing

    assert rotate.main(["--include-backups"]) == 0
    for path in [rotation_dirs / "user_memories" / "alice_memory.json",
                 rotation_dirs / "user_memories" / "plain_memory.json",
                 rotation_dirs / "backups" / "2026" / "alice_memory.json"]:
        raw = path.read_bytes()
        assert raw.startswith(b"FINJAENC1\n")
        assert json.loads(module.decrypt_bytes(raw))[0]["text"] == "remember me"  # the server reads it with the new key

    before = (rotation_dirs / "user_memories" / "alice_memory.json").read_bytes()
    assert rotate.main([]) == 0  # second run: already on the new key, untouched
    assert (rotation_dirs / "user_memories" / "alice_memory.json").read_bytes() == before


def test_rotation_never_replaces_a_file_it_cannot_open(rotation_dirs: Path, monkeypatch) -> None:
    broken = rotation_dirs / "user_memories" / "x_memory.json"
    broken.write_bytes(rotate.encrypt(b"[]", rotate.key_bytes("some-third-key")))
    before = broken.read_bytes()
    assert rotate.main([]) == 1
    assert broken.read_bytes() == before


def test_probe_is_hidden_without_the_token(server, monkeypatch: pytest.MonkeyPatch) -> None:
    module, reported = server
    monkeypatch.delenv("MEMORY_PROBE_TOKEN", raising=False)
    client = TestClient(module.app, raise_server_exceptions=False)
    assert client.get("/diagnostics/probe", params={"token": "x"}).status_code == 404
    assert reported == []


def test_probe_reports_the_real_bug(server, monkeypatch: pytest.MonkeyPatch) -> None:
    module, reported = server
    monkeypatch.setenv("MEMORY_PROBE_TOKEN", TOKEN)
    client = TestClient(module.app, raise_server_exceptions=False)
    response = client.get("/diagnostics/probe", params={"token": TOKEN})
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-530"
    assert isinstance(reported[0], MemoryDiagnosticsProbeError)


def test_the_probe_error_points_flare_at_memory_stats(server) -> None:
    module, _ = server
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="4.5.0")
    assert problem is None and config.project_id == "finja-memory"
    sender = AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())
    try:
        try:
            module.average_memory_importance([])
        except ZeroDivisionError as exc:
            raise MemoryDiagnosticsProbeError("probe", module="finja-memory") from exc
    except MemoryDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event["error"]["code"] == "FINJA-530" and event["error"]["affected_file"] == "memory_stats.py"
