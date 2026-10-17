"""
======================================================================
      Flare (Finja Agentic Code) – Input Exclusion Gate
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Hard exclusion of secrets and private data at intake.

  New in v1.11.0:
    - First version: .env files, key material, credentials and personal
      data directories are refused before anything is staged or sent to
      a model. One source of truth for credential patterns, shared with
      the incident envelope.

----------------------------------------------------------------------

  Flare may only ever see what it needs to repair code. Everything the
  README promises Flare never receives -- Finja's diary, memory, Firebase
  secrets, OpenRouter keys -- used to be a promise about the SENDER. This
  gate makes it a property of the RECEIVER: a submission that contains
  such material is refused before it is staged, stored, logged, or put
  into a model prompt.

  What it enforces, and what it deliberately cannot:

    * Paths are decided by NAME. `.env*`, key material, secret and
      credential directories, and personal-data locations are refused
      whatever the file contains. Data-shaped files (.json .yml .txt ...)
      are also refused by name when the name says "secrets", "tokens",
      "credentials". Source files are NOT: `tokens.py` and `secrets.py`
      are ordinary code, so for source the content decides.
    * Content is decided by SHAPE. Private-key blocks, vendor key
      formats, bearer tokens, credentials inside URLs, and secret-looking
      assignments are refused. This is defence in depth against an
      accident, not a filter against an adversary: a value that is
      obfuscated, split or merely renamed will pass. The sender must
      still strip sensitive material before it submits.
    * Free-text user prompts and diary prose CANNOT be recognised by
      pattern. Only their location and credential-shaped content can be.
      The gate does not claim more than that.

  Fail closed, never echo. A refusal names the file, the line and the
  rule that fired -- all things the sender already knows -- and never the
  matched text. The report is therefore safe to store, return and show.

  Pure logic: no FastAPI, no filesystem, no network.

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
from bisect import bisect_left
from collections.abc import Iterable
from itertools import islice
from pathlib import PurePosixPath

from core.exceptions import SensitiveInputRejectedError
from core.repair_scope import CODE_EXTENSIONS

SCHEMA_VERSION = 1
POLICY = "finja-flare-input-exclusion-v1"
MAX_REPORTED_VIOLATIONS = 25
MAX_MESSAGE_LOCATIONS = 5
MAX_HITS_PER_FILE = 25
MAX_MATCHES_PER_RULE = 2000
NEWLINE_RE = re.compile("\n")
TASK_LOCATION = "<task>"

KIND_SECRET_DIRECTORY = "secret_directory"
KIND_PERSONAL_DATA_DIRECTORY = "personal_data_directory"
KIND_ENV_FILE = "env_file"
KIND_KEY_MATERIAL = "key_material"
KIND_SECRET_FILENAME = "secret_filename"
KIND_CREDENTIAL = "credential"

# Source files are judged by their content: `tokens.py` is a lexer and
# `secrets.py` imports the standard library. Data files are judged by name
# as well, because a file called tokens.json is the token store.
SOURCE_SUFFIXES = frozenset({".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html"})
DATA_SUFFIXES = (CODE_EXTENSIONS - SOURCE_SUFFIXES) | frozenset({""})

# Refused whatever the file type: nothing in these is source code.
SECRET_DIRECTORIES = frozenset({
    "private", "secrets", "credentials", "userdata", "user_data",
    "logs", "backups", "downloads",
    ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".git",
})
# Refused for data files only: a `memory/` package of source code is
# ordinary, a `memory/user_42.json` is somebody's stored conversation.
PERSONAL_DATA_DIRECTORIES = frozenset({
    "diary", "diaries", "memory", "memories", "chat_history", "chat_logs",
    "chatlogs", "conversations", "transcripts", "user_prompts", "user_messages",
})

ENV_FILE_RE = re.compile(r"^\.env|\.env(?:\.|$)")
KEY_MATERIAL_RE = re.compile(
    r"^(?:id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|$)|authorized_keys$|known_hosts$"
    r"|\.npmrc$|\.pypirc$|\.netrc$|.*\.(?:pem|key|p12|pfx|jks|keystore|ppk)$)"
)
# Matched against the stem with separators removed, so api_key, api-key and
# apiKey all read as "apikey".
SECRET_NAME_WORDS = (
    "secret", "credential", "password", "passwd", "apikey", "privatekey",
    "serviceaccount", "adminsdk", "accesstoken", "refreshtoken", "authtoken",
    "bottoken", "clientsecret",
)
# `token` is matched as a whole word only: tokens.json is a token store,
# tokenizer.json is a vocabulary.
SECRET_NAME_TOKENS = frozenset({"token", "tokens"})

PLACEHOLDER_RE = re.compile(r"^(?:<|\$|%|\{\{|\*{3,}|\.{3})")
PLACEHOLDER_WORDS = frozenset({"none", "null", "true", "false", "redacted", "<redacted>"})
# Whole words inside a value that mark it as documentation or a test
# fixture. Matched as words, not prefixes: `test-secret-value` is plainly a
# fixture, while a random token that merely contains the letters "test"
# somewhere is not split into that word. The ecosystem documents in German
# as well, hence dein/beispiel/platzhalter.
FIXTURE_WORDS = frozenset({
    "test", "tests", "testing", "fake", "dummy", "example", "sample", "demo",
    "mock", "placeholder", "changeme", "change", "replace", "your", "xxx",
    "xxxx", "todo", "redacted", "dein", "deine", "beispiel", "platzhalter", "hier",
})
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
URL_VALUE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
# Badge services print a read-only `?token=` into README image URLs on
# purpose; it is public by design, so it is not a leak.
BADGE_HOSTS = ("codecov.io", "shields.io", "badgen.net", "coveralls.io", "badge.fury.io")
URL_HOST_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^/\s?#\"')]+)")
BADGE_LOOKBACK = 400


def _in_badge_url(text: str, offset: int) -> bool:
    """Is this `?token=` part of a URL on a known badge host?"""
    window = text[max(0, offset - BADGE_LOOKBACK):offset]
    hosts = URL_HOST_RE.findall(window)
    return bool(hosts) and hosts[-1].lower().endswith(BADGE_HOSTS)


def _is_placeholder(value: str) -> bool:
    """
    An obviously fake value is documentation, not a leak.

    Applies only to the heuristic rules. The unambiguous formats (private
    key blocks, sk- keys, bot tokens, credentials inside URLs) have no such
    exemption on purpose: a real key does not stop being one because the
    file around it is a test.
    """
    cleaned = value.strip().strip("'\"")
    if not cleaned or cleaned.lower() in PLACEHOLDER_WORDS:
        return True
    if PLACEHOLDER_RE.match(cleaned) or cleaned.endswith(("...", "…")):
        return True
    words = re.split(r"[^a-z0-9]+", CAMEL_BOUNDARY_RE.sub(" ", cleaned).lower())
    return bool(FIXTURE_WORDS.intersection(words))


# A machine secret (an API key, a bot token, a refresh token) is long and
# random. These two shapes are what a test fixture or a code identifier
# looks like instead: `valid_access_token`, `MOCK_TOKEN_2`.
MIN_MACHINE_SECRET_LENGTH = 8
MAX_IDENTIFIER_SEGMENT = 12
IDENTIFIER_LIKE_RE = re.compile(
    r"^(?:[a-z]+(?:[_-][a-z]+)*|[A-Z]+(?:[_-][A-Z]+)*)(?:[_-]?\d{1,4})?$"
)


def _is_benign_value(value: str) -> bool:
    """
    Decide whether a heuristic rule's value is plainly not a machine secret.

    This is a tuning layer for the plain intake only. It is deliberately not
    part of the shared patterns, so the incident envelope -- whose sender
    has already redacted everything -- keeps its original strictness.
    The trade-off is stated plainly: a short or word-like password chosen by
    a human passes here. The gate targets Finja's machine credentials, and a
    Flare that refuses a whole job over `token = "valid_access_token"` in a
    test is one Finja cannot use.
    """
    cleaned = value.strip().strip("'\"")
    return (
        _is_placeholder(cleaned)
        or len(cleaned) < MIN_MACHINE_SECRET_LENGTH
        or _is_identifier_like(cleaned)
    )


def _is_identifier_like(value: str) -> bool:
    """
    Short words joined by separators, e.g. `valid_access_token`.

    The segment cap matters: without it `abcdefghijklmnop1234` also fits
    "lowercase letters plus a few digits". A real identifier is made of
    words; a sixteen-letter unbroken run is not one.
    """
    if not IDENTIFIER_LIKE_RE.match(value):
        return False
    return all(len(segment) <= MAX_IDENTIFIER_SEGMENT for segment in re.split(r"[_\-\d]+", value) if segment)


def _is_benign_yaml_value(value: str) -> bool:
    """URLs, file paths and plain numbers are not secrets, whatever the key says."""
    cleaned = value.strip().strip("'\"")
    return (
        _is_benign_value(cleaned)
        or bool(URL_VALUE_RE.match(cleaned))
        or cleaned.startswith(("/", "./", "../", "~"))
        or cleaned.isdigit()
    )


# Credential shapes that are unambiguous in any file. The incident envelope
# reuses these, so the two intake paths cannot drift apart.
UNIVERSAL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block",
     re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE)),
    # The token part needs a digit or real length, so the two words "Bearer
    # authentication" in a comment read as prose, while the same word
    # followed by an actual credential reads as a header. No example token
    # is written out here: this file is scanned by its own test, and a
    # documentation line with a token-shaped value is exactly what the
    # gate exists to refuse.
    ("bearer_token",
     re.compile(r"\bBearer\s+(?P<value>(?:(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{12,}"
                r"|[A-Za-z0-9._~+/=-]{24,}))", re.IGNORECASE)),
    ("vendor_api_key",
     re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}"
                r"|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b")),
    ("discord_bot_token",
     re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b")),
    ("twitch_oauth",
     re.compile(r"\boauth:[a-z0-9]{30}\b", re.IGNORECASE)),
    # Every repetition below is bounded. An unbounded `[A-Za-z][A-Za-z0-9+.-]*`
    # is tried from every letter of a long run, which turned any minified
    # file or base64 blob into a quadratic scan (a minute for 300 KB). URL
    # schemes, user names and passwords have natural limits, so use them.
    ("url_with_credentials",
     re.compile(r"[A-Za-z][A-Za-z0-9+.-]{0,31}://[^/\s:@]{1,256}:[^@\s/]{1,256}@")),
    ("secret_query_parameter",
     re.compile(r"[?&](?:token|api[_-]?key|secret|auth)=(?P<value>[^\s&]+)", re.IGNORECASE)),
    ("secret_assignment",
     re.compile(r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token"
                r"|bot[_-]?token|client[_-]?secret|private[_-]?key|password|passwd|secret)"
                r"[\"']?\s*[:=]\s*[\"'](?P<value>[^\"'\r\n]{4,})[\"']", re.IGNORECASE)),
)
UNIVERSAL_CREDENTIAL_PATTERNS = tuple(pattern for _, pattern in UNIVERSAL_RULES)

# Shapes that only make sense in a data file. Applied to code they would
# flag `DB_PASSWORD = settings.get(...)`.
_DOTENV_SUFFIXES = frozenset({".txt", ".md", ".yml", ".yaml", ".toml"})
_YAML_SUFFIXES = frozenset({".yml", ".yaml"})
DATA_RULES: tuple[tuple[str, re.Pattern[str], frozenset[str], bool], ...] = (
    ("dotenv_secret_line",
     # `[ \t]` and never `\s`: with MULTILINE, `^\s*` can swallow every blank
     # line after the line start, and a file of nothing but newlines is then
     # rescanned from each of them.
     re.compile(r"^[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]{0,63}(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)"
                r"[ \t]*=[ \t]*(?P<value>\S{8,})[ \t]*$", re.MULTILINE),
     _DOTENV_SUFFIXES, False),
    ("yaml_secret_value",
     re.compile(r"^[ \t]*[\w.-]{0,64}(?:password|passwd|secret|token|api[_-]?key)[\w.-]{0,64}[ \t]*:[ \t]*"
                r"(?P<value>[^\s#'\"{\[<$&*!|>][^\s#]{7,})[ \t]*(?:#.*)?$",
                re.IGNORECASE | re.MULTILINE),
     _YAML_SUFFIXES, True),
)


def path_violation(path: str) -> tuple[str, str] | None:
    """
    Decide a path by name alone. Returns (kind, rule) or None.

    Works on the raw string a caller sent, before any other validation, so
    it normalises separators and case itself.
    """
    parts = [part for part in str(path).replace("\\", "/").casefold().split("/") if part]
    if not parts:
        return None
    directories, name = parts[:-1], parts[-1]
    suffix = PurePosixPath(name).suffix
    is_data = suffix in DATA_SUFFIXES

    for directory in directories:
        if directory in SECRET_DIRECTORIES:
            return KIND_SECRET_DIRECTORY, f"directory '{directory}'"
    if ENV_FILE_RE.search(name):
        return KIND_ENV_FILE, "environment file"
    if KEY_MATERIAL_RE.match(name):
        return KIND_KEY_MATERIAL, "key material"
    if is_data:
        for directory in directories:
            if directory in PERSONAL_DATA_DIRECTORIES:
                return KIND_PERSONAL_DATA_DIRECTORY, f"data under '{directory}'"
        stem = PurePosixPath(name).stem
        squashed = re.sub(r"[^a-z0-9]", "", stem)
        words = set(re.split(r"[^a-z0-9]+", stem))
        if any(word in squashed for word in SECRET_NAME_WORDS) or words & SECRET_NAME_TOKENS:
            return KIND_SECRET_FILENAME, "secret-like file name"
    return None


def structurally_unsafe(path: str) -> bool:
    """
    Backslashes, absolute paths and `.` / `..` segments are a path-safety
    failure, not a secrets failure. The payload path validation owns those
    and answers 400; the name rules would only relabel an attempted
    traversal such as `../etc/passwd` as "secret-like file name" (422) and
    hide what actually went wrong.
    """
    text = str(path)
    return "\\" in text or text.startswith("/") \
        or any(part in {".", ".."} for part in text.split("/"))


def scan_text(text: str, suffix: str = "") -> list[tuple[str, int]]:
    """Return (rule, line) for every credential-shaped span. Never the span itself."""
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    newlines: list[int] = []
    indexed = False

    def line_at(offset: int) -> int:
        # Built once and only when the first hit needs it, then a binary
        # search. Counting newlines up to every offset made a single line
        # holding thousands of hits quadratic. The line of an offset is the
        # number of line breaks before it, plus one.
        nonlocal indexed
        if not indexed:
            newlines.extend(m.start() for m in NEWLINE_RE.finditer(text))
            indexed = True
        return bisect_left(newlines, offset) + 1

    def record(rule: str, offset: int) -> None:
        item = (rule, line_at(offset))
        if item not in seen:
            seen.add(item)
            found.append(item)

    def full() -> bool:
        # One refused file needs a handful of locations, not ten thousand.
        # Each location costs a scan up to its offset to find the line, so
        # an unbounded count would make a file full of hits quadratic.
        return len(found) >= MAX_HITS_PER_FILE

    for rule, pattern in UNIVERSAL_RULES:
        for match in islice(pattern.finditer(text), MAX_MATCHES_PER_RULE):
            if full():
                break
            value = match.groupdict().get("value")
            if value is not None and _is_benign_value(value):
                continue
            if rule == "secret_query_parameter" and _in_badge_url(text, match.start()):
                continue
            record(rule, match.start())
    for rule, pattern, suffixes, strict_values in DATA_RULES:
        if suffix.lower() not in suffixes:
            continue
        for match in islice(pattern.finditer(text), MAX_MATCHES_PER_RULE):
            if full():
                break
            value = match.group("value")
            if (_is_benign_yaml_value(value) if strict_values else _is_benign_value(value)):
                continue
            record(rule, match.start())
    return sorted(found, key=lambda item: (item[1], item[0]))


def review_submission(*, task: str, files: Iterable[tuple[str, str]]) -> dict:
    """Review a whole submission. The report holds locations and rules, never content."""
    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "policy": POLICY,
        "files_checked": 0,
        "violations": [],
        "violations_truncated": False,
        "echoes_input": False,
        "verdict": "clean",
    }
    violations: list[dict] = []

    for path, content in files:
        report["files_checked"] += 1
        # Structurally unsafe paths are refused later by the payload path
        # validation (400). Their content is still scanned below.
        denied = None if structurally_unsafe(path) else path_violation(path)
        if denied is not None:
            kind, rule = denied
            violations.append({"kind": kind, "path": path, "line": None, "rule": rule})
            continue
        suffix = PurePosixPath(str(path).replace("\\", "/")).suffix
        for rule, line in scan_text(content, suffix):
            violations.append({"kind": KIND_CREDENTIAL, "path": path, "line": line, "rule": rule})

    for rule, line in scan_text(task):
        violations.append({"kind": KIND_CREDENTIAL, "path": TASK_LOCATION, "line": line, "rule": rule})

    if len(violations) > MAX_REPORTED_VIOLATIONS:
        report["violations_truncated"] = True
        violations = violations[:MAX_REPORTED_VIOLATIONS]
    report["violations"] = violations
    if violations:
        report["verdict"] = "refused"
    return report


def enforce(report: dict) -> None:
    """Turn a refusal into the structured code Finja can show a user."""
    if report.get("verdict") != "refused":
        return
    violations = report.get("violations", [])
    locations = []
    for item in violations[:MAX_MESSAGE_LOCATIONS]:
        where = item["path"] if item.get("line") is None else f"{item['path']}:{item['line']}"
        locations.append(f"{where} ({item['kind']})")
    more = len(violations) - MAX_MESSAGE_LOCATIONS
    suffix = f" and {more} more" if more > 0 else ""
    raise SensitiveInputRejectedError(
        "Submission refused before staging; it holds secrets or private data: "
        + ", ".join(locations) + suffix
        + ". Remove them and resubmit."
    )
