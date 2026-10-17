#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Input Exclusion Gate Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit and intake tests for the hard exclusion of secrets
               and private data (core/privacy_gate.py, FLARE-612).

               A gate that refuses everything is useless and a gate that
               refuses nothing is a promise on paper, so the tests pin
               both directions: what must be refused, what must pass, and
               that a refusal never repeats the secret it found.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the input exclusion gate itself.

  Fixture secrets are assembled from parts on purpose. A literal key in
  this file would trip every secret scanner and every reader, and the point
  of the gate is that none of these shapes sits in a tree unnoticed.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import json
import sys
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import incident_envelope, privacy_gate  # noqa: E402
from core.exceptions import SensitiveInputRejectedError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# --- fixture secrets, never written as one literal --------------------------
OPENROUTER_LIKE = "sk-" + "or-v1-" + "a1b2c3d4e5f6" * 3
GITHUB_LIKE = "ghp_" + "A1b2" * 9
AWS_LIKE = "AKIA" + "ABCDEFGHIJKLMNOP"
SLACK_LIKE = "xoxb-" + "1234567890-abcdefghij"
DISCORD_LIKE = "M" + "a1B2c3D4e5F6g7H8i9J0k1L2" + "." + "Xy12Zq" + "." + "AbCd1234EfGh5678IjKl9012MnOp"
TWITCH_LIKE = "oauth:" + "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5"
PRIVATE_KEY_BLOCK = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow\n-----END " + "RSA PRIVATE KEY-----\n"
URL_WITH_PASSWORD = "postgres://" + "admin:" + "s3cr3tpw" + "@db.example.invalid/app"
RANDOM_VALUE = "Zx9Qw3Er7Ty1Ui5Op8As2Df6Gh4Jk0Lq"
# Names and shapes that would read as a leak if written out in this file.
API_KEY_NAME = "API_" + "KEY"
ENV_API_KEY_NAME = "OPENROUTER_" + API_KEY_NAME
CLIENT_SECRET_NAME = "SPOTIFY_CLIENT_" + "SECRET"
BEARER_LOOKING = "Bearer " + "abcdefghijklmnop" + "1234"
ETC_PASSWD = "etc" + "/passwd"
# chr(92) is a backslash. Two of them around a word, written out as a
# literal, read as a network share path to the repository scanner.
BACKSLASH_PATH = "a" + chr(92) + "b" + chr(92) + "tokens.json"


def _assign(name: str, value: str) -> str:
    """`NAME = "value"` assembled at run time, so no assignment literal sits in this file."""
    return f'{name} = "{value}"\n'


def _review(path: str, content: str, task: str = "Fix the bug") -> dict:
    return privacy_gate.review_submission(task=task, files=[(path, content)])


def _rules(path: str, content: str) -> set[str]:
    return {item["rule"] for item in _review(path, content)["violations"]}


# ==============================================================================
# Paths are refused by name
# ==============================================================================

class TestPathExclusion:

    @pytest.mark.parametrize("path,kind", [
        ("config/.env", "env_file"),
        (".env", "env_file"),
        ("prod.env.txt", "env_file"),
        ("local.env", "env_file"),
        ("app/.env.production", "env_file"),
        (".envrc", "env_file"),
        ("id_rsa", "key_material"),
        ("deploy/id_ed25519.txt", "key_material"),
        ("certs/server.pem", "key_material"),
        ("certs/server.key", "key_material"),
        ("a/.npmrc", "key_material"),
        ("private/notes.txt", "secret_directory"),
        ("secrets/anything.py", "secret_directory"),
        ("credentials/x.json", "secret_directory"),
        ("data/logs/app.json", "secret_directory"),
        ("backups/db.yml", "secret_directory"),
        ("home/.ssh/config", "secret_directory"),
        ("diary/2026-10-17.md", "personal_data_directory"),
        ("memory/user_42.json", "personal_data_directory"),
        ("data/conversations/a.json", "personal_data_directory"),
        ("chat_history/room.txt", "personal_data_directory"),
        ("secrets.json", "secret_filename"),
        ("tokens.json", "secret_filename"),
        ("spotify_token.json", "secret_filename"),
        ("credentials.yml", "secret_filename"),
        ("api_key.txt", "secret_filename"),
        ("firebase-adminsdk-abc.json", "secret_filename"),
        ("service-account.json", "secret_filename"),
    ])
    def test_sensitive_paths_are_refused(self, path: str, kind: str) -> None:
        assert privacy_gate.path_violation(path) is not None, path
        assert privacy_gate.path_violation(path)[0] == kind

    @pytest.mark.parametrize("path", [
        "demo.py",
        "core/memory.py",           # a memory PACKAGE is code, not somebody's conversations
        "memory/store.py",
        "diary/render.py",
        "secrets.py",               # the stdlib module name, and plenty of real code
        "tokens.py",                # a lexer
        "tokenizer.json",           # a vocabulary, not a token store
        "env.py",                   # not an environment file
        "environment.py",
        "src/token_utils.py",
        "docs/password_reset_flow.py",
        "finja-memory/README.md",   # a project NAME that contains "memory"
        "README.md",
        "config/settings.yml",
    ])
    def test_ordinary_code_paths_pass(self, path: str) -> None:
        assert privacy_gate.path_violation(path) is None, path

    def test_path_rules_ignore_case_and_separator_style(self) -> None:
        """The real repository stores `Memory/` with a capital M."""
        assert privacy_gate.path_violation("Finja-music/Memory/memory.json") is not None
        assert privacy_gate.path_violation("PRIVATE/x.py") is not None
        assert privacy_gate.path_violation("private\\x.py") is not None

    def test_a_refused_path_is_not_also_scanned_for_content(self) -> None:
        """The name already decided; the report must not grow noise per file."""
        report = _review("prod.env.txt", "API_KEY = " + '"' + RANDOM_VALUE + '"')
        assert [v["kind"] for v in report["violations"]] == ["env_file"]


# ==============================================================================
# Content is refused by shape
# ==============================================================================

class TestContentExclusion:

    @pytest.mark.parametrize("label,content,rule", [
        ("openrouter key", f'KEY = "{OPENROUTER_LIKE}"\n', "vendor_api_key"),
        ("github token", f'T = "{GITHUB_LIKE}"\n', "vendor_api_key"),
        ("aws access key id", f'ID = "{AWS_LIKE}"\n', "vendor_api_key"),
        ("slack token", f'T = "{SLACK_LIKE}"\n', "vendor_api_key"),
        ("discord bot token", f'TOKEN = "{DISCORD_LIKE}"\n', "discord_bot_token"),
        ("twitch oauth", f'PASS = "{TWITCH_LIKE}"\n', "twitch_oauth"),
        ("private key block", PRIVATE_KEY_BLOCK, "private_key_block"),
        ("password in url", f'U = "{URL_WITH_PASSWORD}"\n', "url_with_credentials"),
        ("token in query", 'U = "https://api.example.invalid/x?token=' + RANDOM_VALUE + '"\n', "secret_query_parameter"),
        ("bearer header", 'H = {"Authorization": "Bearer ' + RANDOM_VALUE + '"}\n', "bearer_token"),
        ("random secret literal", 'API_KEY = "' + RANDOM_VALUE + '"\n', "secret_assignment"),
        ("random password literal", 'password = "' + RANDOM_VALUE + '"\n', "secret_assignment"),
        ("json secret", '{"client_secret": "' + RANDOM_VALUE + '"}\n', "secret_assignment"),
        ("self attribute", 'self.refresh_token = "' + RANDOM_VALUE + '"\n', "secret_assignment"),
    ])
    def test_credential_shapes_are_refused(self, label: str, content: str, rule: str) -> None:
        assert rule in _rules("demo.py", content), label

    def test_a_long_unbroken_lowercase_run_is_not_waved_through_as_an_identifier(self) -> None:
        assert "bearer_token" in _rules("demo.py", f'H = "{BEARER_LOOKING}"\n')
        assert "secret_assignment" in _rules("demo.py", 'password = "hunter2hunter2"\n')

    def test_the_first_line_of_a_hit_is_reported(self) -> None:
        content = "x = 1\ny = 2\n" + f'KEY = "{OPENROUTER_LIKE}"\n'
        violation = _review("demo.py", content)["violations"][0]
        assert violation["path"] == "demo.py"
        assert violation["line"] == 3

    @pytest.mark.parametrize("path,content,rule", [
        ("conf.yml", "db:\n  password: " + RANDOM_VALUE + "\n", "yaml_secret_value"),
        ("notes.txt", f"{ENV_API_KEY_NAME}=" + RANDOM_VALUE + "\n", "dotenv_secret_line"),
        ("README.md", f"```\n{CLIENT_SECRET_NAME}=" + RANDOM_VALUE + "\n```\n", "dotenv_secret_line"),
    ])
    def test_data_file_shapes_are_refused(self, path: str, content: str, rule: str) -> None:
        assert rule in _rules(path, content)

    def test_unambiguous_formats_have_no_test_exemption(self) -> None:
        """A real key does not stop being one because the file around it is a test."""
        content = 'KEY = "sk-' + "test-" + "0123456789abcdef" + '"  # test fixture\n'
        assert "vendor_api_key" in _rules("test_client.py", content)


class TestOrdinaryContentPasses:
    """The other direction. A gate that refuses normal code cannot be used."""

    @pytest.mark.parametrize("content", [
        "# Use Bearer authentication for this endpoint\n",
        "token_count = 3\n",
        'password_policy = {"min_length": 12}\n',
        'API_KEY = os.environ["API_KEY"]\n',
        'secret_santa = "gift exchange"\n',
        'headers = {"Authorization": "Bearer " + token}\n',
        'TOKEN = "valid_access_token"\n',
        _assign("MOCK_" + API_KEY_NAME, "MOCK_" + API_KEY_NAME + "_2"),
        _assign("pass" + "word", "test-pass" + "word-123"),
        _assign("sec" + "ret", ""),
        _assign("api_" + "key", "<your-api-" + "key>"),
        _assign("SECRET_" + "KEY", "${" + "SECRET_KEY}"),
        '{"client_secret": "your_client_secret"}\n',
        'def count_tokens(text):\n    return len(text.split())\n',
        'client = Client(api_key=settings.API_KEY, password=get_password())\n',
    ])
    def test_ordinary_source_is_not_refused(self, content: str) -> None:
        assert _review("demo.py", content)["verdict"] == "clean", content

    @pytest.mark.parametrize("path,content", [
        ("conf.yml", "limits:\n  max_tokens: 100000000\n"),
        ("conf.yml", "auth:\n  token_url: https://auth.example.invalid/oauth/token\n"),
        ("conf.yml", "db:\n  password_file: /run/secrets/db_pw\n"),
        ("conf.yml", "db:\n  password: ${DB_PASSWORD}\n"),
        ("conf.yml", 'api_key: "<your key>"\n'),
        ("README.md", "OPENROUTER_API_KEY=your-key-here\n"),
        ("README.md", "SPOTIFY_CLIENT_SECRET=abc123...\n"),
        ("README.md", "DB_PASSWORD=\n"),
        ("README.md", "[![codecov](https://codecov.io/gh/o/r/branch/main/graph/badge.svg?token=AB12CD34EF)](https://codecov.io/gh/o/r)\n"),
    ])
    def test_ordinary_data_and_docs_are_not_refused(self, path: str, content: str) -> None:
        assert _review(path, content)["verdict"] == "clean", (path, content)

    def test_known_limit_a_short_human_password_passes(self) -> None:
        """
        Stated plainly rather than hidden: the gate targets machine credentials,
        which are long and random. A seven-character password a person chose
        is below that line. The sender must still strip it.
        """
        assert _review("demo.py", 'password = "hunter2"\n')["verdict"] == "clean"

    def test_known_limit_free_text_prompts_cannot_be_recognised(self) -> None:
        """
        A user's chat message or a diary sentence has no credential shape.
        Only its location (diary/, memory/) and credential-shaped content
        can be refused; prose in an ordinary file is indistinguishable from
        a comment.
        """
        prose = '# The user wrote: "please sing me a song, I am sad today"\n'
        assert _review("demo.py", prose)["verdict"] == "clean"


class TestRealSourceTree:
    """
    The strongest false-positive test available: the module's own source.
    Test files are left out because they necessarily contain fixtures.
    """

    SOURCES = (
        sorted((_MODULE_ROOT / "core").glob("*.py"))
        + sorted((_MODULE_ROOT / "worker").glob("*.py"))
        + sorted((_MODULE_ROOT / "worker-broken").glob("*.py"))
        + [_MODULE_ROOT / "orchestrator" / "app" / "main.py",
           _MODULE_ROOT / "testbed" / "run_testbed.py",
           _MODULE_ROOT / "docker-compose.yml",
           _MODULE_ROOT / "docker-compose.testbed.yml",
           _MODULE_ROOT / "README.md",
           _MODULE_ROOT / "orchestrator" / "requirements.txt"]
    )

    @pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.relative_to(_MODULE_ROOT).as_posix())
    def test_the_modules_own_source_is_accepted(self, source: Path) -> None:
        relative = source.relative_to(_MODULE_ROOT).as_posix()
        report = _review(relative, source.read_text(encoding="utf-8"))
        assert report["verdict"] == "clean", report["violations"]

    def test_the_env_template_is_refused_by_design(self) -> None:
        """Even a template: `.env.example` is where real values get pasted by mistake."""
        assert privacy_gate.path_violation(".env.example") is not None


# ==============================================================================
# A refusal never repeats the secret it found
# ==============================================================================

class TestNeverEchoes:

    CASES = [
        ("demo.py", f'KEY = "{OPENROUTER_LIKE}"\n', OPENROUTER_LIKE),
        ("demo.py", PRIVATE_KEY_BLOCK, "MIIEow"),
        ("demo.py", f'U = "{URL_WITH_PASSWORD}"\n', "s3cr3tpw"),
        ("demo.py", 'password = "' + RANDOM_VALUE + '"\n', RANDOM_VALUE),
        ("conf.yml", "db:\n  password: " + RANDOM_VALUE + "\n", RANDOM_VALUE),
    ]

    @pytest.mark.parametrize("path,content,secret", CASES)
    def test_report_and_error_hold_no_secret_value(self, path: str, content: str, secret: str) -> None:
        report = _review(path, content)
        assert report["verdict"] == "refused"
        assert report["echoes_input"] is False
        assert secret not in json.dumps(report)

        with pytest.raises(SensitiveInputRejectedError) as excinfo:
            privacy_gate.enforce(report)
        assert secret not in str(excinfo.value)
        assert excinfo.value.code == "FLARE-612"

    def test_a_secret_in_the_task_is_located_but_not_repeated(self) -> None:
        report = privacy_gate.review_submission(
            task=f"Fix it, my key is {OPENROUTER_LIKE}", files=[("demo.py", "x = 1\n")]
        )
        assert report["violations"][0]["path"] == privacy_gate.TASK_LOCATION
        assert OPENROUTER_LIKE not in json.dumps(report)

    def test_the_message_names_a_file_and_line_the_sender_already_knows(self) -> None:
        report = _review("demo.py", "x = 1\n" + f'KEY = "{OPENROUTER_LIKE}"\n')
        with pytest.raises(SensitiveInputRejectedError) as excinfo:
            privacy_gate.enforce(report)
        assert "demo.py:2" in str(excinfo.value)
        assert "credential" in str(excinfo.value)


class TestSubmissionReview:

    def test_a_clean_submission_counts_its_files(self) -> None:
        report = privacy_gate.review_submission(
            task="Fix the bug", files=[("a.py", "x = 1\n"), ("b.py", "y = 2\n")]
        )
        assert report["verdict"] == "clean"
        assert report["files_checked"] == 2
        privacy_gate.enforce(report)  # raises nothing

    def test_every_offending_file_is_reported_not_just_the_first(self) -> None:
        report = privacy_gate.review_submission(
            task="Fix the bug",
            files=[("tokens.json", "{}"), ("demo.py", f'K = "{OPENROUTER_LIKE}"\n'), ("ok.py", "x = 1\n")],
        )
        assert {v["path"] for v in report["violations"]} == {"tokens.json", "demo.py"}

    def test_the_report_is_bounded(self) -> None:
        files = [(f"tokens_{index}.json", "{}") for index in range(privacy_gate.MAX_REPORTED_VIOLATIONS + 10)]
        report = privacy_gate.review_submission(task="x", files=files)
        assert len(report["violations"]) == privacy_gate.MAX_REPORTED_VIOLATIONS
        assert report["violations_truncated"] is True

    def test_the_message_is_bounded_too(self) -> None:
        files = [(f"tokens_{index}.json", "{}") for index in range(12)]
        with pytest.raises(SensitiveInputRejectedError) as excinfo:
            privacy_gate.enforce(privacy_gate.review_submission(task="x", files=files))
        assert str(excinfo.value).count("tokens_") == privacy_gate.MAX_MESSAGE_LOCATIONS
        assert "and 7 more" in str(excinfo.value)


# ==============================================================================
# At the door: POST /jobs
# ==============================================================================

class TestIntake:

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(main, "DEDUPE_WINDOW_SECONDS", 0)
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()
        self.jobs = tmp_path / "jobs"
        self.client = TestClient(main.app)

    def _staged_jobs(self) -> list[str]:
        if not self.jobs.exists():
            return []
        return [entry.name for entry in self.jobs.iterdir() if main.JOB_ID_RE.fullmatch(entry.name)]

    def _post(self, files: list[dict], task: str = "Fix the bug", **headers):
        return self.client.post(
            "/jobs", json={"task": task, "repository": "t", "files": files}, headers=headers
        )

    def test_a_secret_in_source_is_refused_with_422_and_flare_612(self) -> None:
        response = self._post([{"path": "demo.py", "content": f'KEY = "{OPENROUTER_LIKE}"\n'}])

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "FLARE-612"
        assert "demo.py:1" in detail["message"]
        assert OPENROUTER_LIKE not in response.text

    def test_a_refusal_leaves_nothing_on_disk(self) -> None:
        """The whole point: a refused submission is never stored."""
        self._post([{"path": "demo.py", "content": f'KEY = "{OPENROUTER_LIKE}"\n'}])
        self._post([{"path": "tokens.json", "content": "{}"}])
        assert self._staged_jobs() == []
        if self.jobs.exists():
            assert not list(self.jobs.rglob("request.json"))
            assert not list(self.jobs.rglob("workspace"))

    @pytest.mark.parametrize("path", ["secrets.json", "config/.env", "diary/entry.md", "memory/u.json", "id_rsa.txt"])
    def test_sensitive_paths_are_refused_at_the_door(self, path: str) -> None:
        response = self._post([{"path": path, "content": "x\n"}])
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "FLARE-612"

    @pytest.mark.parametrize("path", [
        "../" + ETC_PASSWD, "/" + ETC_PASSWD, "pkg/../../secrets.json", BACKSLASH_PATH,
    ])
    def test_a_path_traversal_stays_a_path_error_not_a_secrets_error(self, path: str) -> None:
        """
        `../etc/passwd` also looks like a secret-ish file name. The structural
        failure must win, otherwise an attempted escape gets relabelled and
        the real reason is hidden behind a policy message.
        """
        response = self._post([{"path": path, "content": "x = 1\n"}])
        assert response.status_code == 400, path
        # The path validation answers with a plain-text detail, the gate with
        # a structured code; seeing no FLARE-612 proves which one spoke.
        assert "FLARE-612" not in response.text

    def test_a_root_env_file_gets_the_secrets_reason_not_the_dotfile_one(self) -> None:
        """The payload validation would call `.env` merely an unsafe path (400)."""
        response = self._post([{"path": ".env", "content": "A=1\n"}])
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "FLARE-612"

    def test_content_in_a_structurally_unsafe_file_is_still_scanned(self) -> None:
        response = self._post([{"path": "../x.py", "content": f'KEY = "{OPENROUTER_LIKE}"\n'}])
        assert response.status_code == 422
        assert OPENROUTER_LIKE not in response.text

    def test_a_secret_in_the_task_text_is_refused(self) -> None:
        response = self._post([{"path": "demo.py", "content": "x = 1\n"}], task=f"my key is {OPENROUTER_LIKE}")
        assert response.status_code == 422
        assert OPENROUTER_LIKE not in response.text
        assert self._staged_jobs() == []

    def test_ordinary_code_is_still_accepted_and_staged(self) -> None:
        response = self._post([{"path": "demo.py", "content": "def add(a, b):\n    return a - b\n"}])
        assert response.status_code == 200
        assert len(self._staged_jobs()) == 1

    def test_a_refused_submission_does_not_block_the_cleaned_one(self) -> None:
        dirty = [{"path": "demo.py", "content": f'KEY = "{OPENROUTER_LIKE}"\n'}]
        clean = [{"path": "demo.py", "content": 'KEY = os.environ["KEY"]\n'}]
        assert self._post(dirty).status_code == 422
        retried = self._post(clean)
        assert retried.status_code == 200
        assert retried.json()["deduplicated"] is False

    def test_the_gate_judges_the_decrypted_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Under transport encryption the secret is inside the envelope, so the gate must run after it opens."""
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "gate-test-transport-key")
        sealed = main.seal_json({
            "task": "Fix the bug", "repository": "t",
            "files": [{"path": "demo.py", "content": f'KEY = "{OPENROUTER_LIKE}"\n'}],
        })
        response = self.client.post("/jobs", json=sealed)

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "FLARE-612"
        assert self._staged_jobs() == []

    def test_an_encrypted_clean_submission_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "gate-test-transport-key")
        sealed = main.seal_json({
            "task": "Fix the bug", "repository": "t",
            "files": [{"path": "demo.py", "content": "x = 1\n"}],
        })
        assert self.client.post("/jobs", json=sealed).status_code == 200


# ==============================================================================
# One source of truth with the incident envelope
# ==============================================================================

class TestEnvelopeSharing:

    def test_the_envelope_reuses_every_shared_credential_pattern(self) -> None:
        for pattern in privacy_gate.UNIVERSAL_CREDENTIAL_PATTERNS:
            assert pattern in incident_envelope.SENSITIVE_PATTERNS

    @pytest.mark.parametrize("value", [AWS_LIKE, SLACK_LIKE, DISCORD_LIKE, TWITCH_LIKE])
    def test_the_envelope_now_also_catches_the_newer_vendor_shapes(self, value: str) -> None:
        assert incident_envelope._has_sensitive_data(f'x = "{value}"')

    def test_the_envelope_stays_strictly_stricter_than_the_intake(self) -> None:
        """
        Intentional asymmetry: an envelope is already redacted by its sender,
        so any bearer-looking token there is a leak, while the plain intake
        must not refuse a job over the words "Bearer authentication".
        """
        header = "Authorization: Bearer abcdefghijklmnop"
        assert incident_envelope._has_sensitive_data(header)
        assert "bearer_token" not in {rule for rule, _ in privacy_gate.scan_text(header)}

    def test_the_envelope_applies_the_same_path_exclusions(self) -> None:
        assert incident_envelope._source_path_allowed("diary/entry.md") is False
        assert incident_envelope._source_path_allowed("secrets.json") is False
        assert incident_envelope._source_path_allowed("memory/store.py") is True


# ==============================================================================
# The test-track catalog must agree with the gate
# ==============================================================================

class TestScanCost:
    """
    A single request must not be able to burn minutes of CPU while holding the
    interpreter lock. Measured before the patterns were bounded: a run of
    letters followed by `://` cost 0.04 s at 8,000 characters and 0.6 s at
    32,000 -- quadratic -- so one 300,000-character file took about a minute,
    and 20 of them a quarter of an hour. Any long identifier, minified line or
    base64 blob triggered it, not only a deliberate attack. A file of nothing
    but blank lines was worse: 15 s at 40,000 characters.

    The size below is far past where a quadratic scan is already slow
    (seconds) and far above where a linear one is not (milliseconds), so the
    budget separates the two with room to spare on a slow CI machine.
    """

    SIZE = 150_000
    BUDGET_SECONDS = 2.0

    GENERATORS = {
        "letters then ://": lambda n: "a" * n + "://x:y",
        "letters only": lambda n: "a" * n,
        "word dots": lambda n: "a." * (n // 2),
        "email-like at signs": lambda n: "a@" * (n // 2),
        "blank lines": lambda n: "\n" * n,
        "whitespace lines": lambda n: " \n" * (n // 2),
        "spaces then text": lambda n: " " * n + "x",
        "keyword then spaces": lambda n: "pass" + "word" + " " * n + "x",
        "keyword repeated": lambda n: ("pass" + "word") * (n // 8),
        "upper-case name": lambda n: "A_" * (n // 2),
        "bearer then letters": lambda n: "Bearer " + "a" * n,
        "bearer repeated": lambda n: "Bearer a " * (n // 8),
        "digits": lambda n: "1" * n,
        "oauth repeated": lambda n: "oauth:" * (n // 6),
        "dotted quad lookalike": lambda n: "1." * (n // 2),
        "vendor prefix repeated": lambda n: "sk-" * (n // 3),
        "quote chain": lambda n: ("pass" + "word=\"") * (n // 10),
        "yaml key then run": lambda n: "token: " + "x" * n,
        "query repeated": lambda n: "?token=" * (n // 7),
    }

    @pytest.mark.parametrize("name", list(GENERATORS))
    @pytest.mark.parametrize("suffix", [".py", ".yml", ".txt"])
    def test_the_gate_scans_hostile_input_in_linear_time(self, name: str, suffix: str) -> None:
        import time

        text = self.GENERATORS[name](self.SIZE)
        started = time.perf_counter()
        privacy_gate.scan_text(text, suffix)
        elapsed = time.perf_counter() - started
        assert elapsed < self.BUDGET_SECONDS, f"{name} {suffix} took {elapsed:.2f}s"

    @pytest.mark.parametrize("name", list(GENERATORS))
    def test_the_envelope_scans_hostile_input_in_linear_time(self, name: str) -> None:
        import time

        text = self.GENERATORS[name](self.SIZE)
        started = time.perf_counter()
        incident_envelope._has_sensitive_data(text)
        elapsed = time.perf_counter() - started
        assert elapsed < self.BUDGET_SECONDS, f"{name} took {elapsed:.2f}s"

    def test_a_whole_submission_of_maximum_size_hostile_files_stays_cheap(self) -> None:
        """20 files of 300,000 characters is the largest request the schema allows."""
        import time

        files = [(f"f{index}.py", ("a" * 299_000) + "://x:y") for index in range(20)]
        started = time.perf_counter()
        report = privacy_gate.review_submission(task="Fix the bug", files=files)
        elapsed = time.perf_counter() - started
        assert report["verdict"] == "clean"
        assert elapsed < 5.0, f"the largest allowed submission took {elapsed:.2f}s"

    def test_bounding_the_patterns_did_not_blind_them(self) -> None:
        long_local_part = "u" * 100 + "@" + "mail.example.invalid"
        assert incident_envelope._has_sensitive_data(f"contact {long_local_part}"), (
            "a local part longer than the 64-character limit must still be caught by its tail"
        )
        assert "url_with_credentials" in _rules("demo.py", f'U = "{URL_WITH_PASSWORD}"\n')
        assert "dotenv_secret_line" in _rules("notes.txt", "\n\n\n\n" + f"{ENV_API_KEY_NAME}={RANDOM_VALUE}\n")
        yaml_text = "\n".join(["db:", "", "", "  password: " + RANDOM_VALUE, ""])
        assert "yaml_secret_value" in _rules("conf.yml", yaml_text)

    def test_line_numbers_stay_exact_after_the_lookup_became_a_binary_search(self) -> None:
        key = OPENROUTER_LIKE
        cases = {
            "first line": (f'K = "{key}"\n', 1),
            "third line": (f'a\nb\nK = "{key}"\n', 3),
            "no line break at all": (f'K = "{key}"', 1),
            "last line after blank ones": (f'a\n\n\nb\nK = "{key}"', 5),
            "windows line endings": (f'a\r\nb\r\nK = "{key}"\r\n', 3),
        }
        for label, (text, line) in cases.items():
            assert privacy_gate.scan_text(text, ".py") == [("vendor_api_key", line)], label

    def test_a_file_full_of_hits_reports_a_bounded_number(self) -> None:
        text = "".join(f'K{n} = "{OPENROUTER_LIKE}{n}"\n' for n in range(500))
        assert len(privacy_gate.scan_text(text, ".py")) <= privacy_gate.MAX_HITS_PER_FILE

    def test_thousands_of_hits_on_one_line_do_not_slow_the_scan(self) -> None:
        import time

        text = ("pass" + 'word="' + "Zx9Qw3Er7Ty1Ui5Op8As" + '" ') * 20_000
        started = time.perf_counter()
        privacy_gate.scan_text(text, ".py")
        assert time.perf_counter() - started < self.BUDGET_SECONDS


class TestCatalogAgreement:
    """
    The live track needs Docker for the control scenario, so this keeps the
    catalog honest without it: every privacy_* scenario is replayed through
    the gate and must get the verdict its expectation claims.
    """

    SCENARIOS = [
        scenario for scenario in json.loads(
            (_MODULE_ROOT / "testbed" / "scenarios.json").read_text(encoding="utf-8")
        )["scenarios"]
        if scenario["name"].startswith("privacy_")
    ]

    def test_the_catalog_holds_the_privacy_scenarios(self) -> None:
        names = {scenario["name"] for scenario in self.SCENARIOS}
        assert "privacy_leaves_ordinary_code_alone" in names
        assert len(names) >= 6

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario["name"])
    def test_the_gate_gives_each_scenario_its_expected_verdict(self, scenario: dict) -> None:
        report = privacy_gate.review_submission(
            task=scenario["task"],
            files=[(entry["path"], entry["content"]) for entry in scenario["files"]],
        )
        if scenario["expect"].get("submit_status") == 422:
            assert report["verdict"] == "refused", scenario["name"]
            assert scenario["expect"]["error_code"] == "FLARE-612"
        else:
            assert report["verdict"] == "clean", (scenario["name"], report["violations"])


# ==============================================================================
# The error code
# ==============================================================================

class TestErrorContract:

    def test_flare_612_is_registered_and_mapped_to_422(self) -> None:
        error = SensitiveInputRejectedError()
        assert error.code == "FLARE-612"
        assert error.for_status()["module"] == "pipeline"
