#!/usr/bin/env python3
"""
Finja monorepo dependency guard.

Scans real Python imports and compares them to the nearest requirements*.txt
(and optional pyproject.toml / requirements.in).

Usage:
  python tools/dependency_guard.py
  python tools/dependency_guard.py --root .
  python tools/dependency_guard.py --strict          # also fail on unused pins
  python tools/dependency_guard.py --json report.json
  python tools/dependency_guard.py --module finja-weather

Exit codes:
  0 = clean (or only warnings)
  1 = missing third-party imports not declared in requirements
  2 = usage / tooling error
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Import name (top-level) -> PyPI / requirements distribution name
# ---------------------------------------------------------------------------
IMPORT_TO_DIST: Dict[str, str] = {
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "flask_cors": "Flask-CORS",
    "discord": "discord.py",
    "faster_whisper": "faster-whisper",
    "speech_recognition": "SpeechRecognition",
    "pygetwindow": "PyGetWindow",
    "mss": "mss",
    "spotipy": "spotipy",
    "docker": "docker",
    "cairosvg": "CairoSVG",
    "rapidocr": "rapidocr",
    "onnxruntime": "onnxruntime",
    "cryptography": "cryptography",
    "langchain_core": "langchain-core",
    "langchain_ollama": "langchain-ollama",
    "langchain_community": "langchain-community",
    "langgraph": "langgraph",
    "openai": "openai",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "starlette": "starlette",
    "pydantic": "pydantic",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "aiofiles": "aiofiles",
    "requests": "requests",
    "urllib3": "urllib3",
    "numpy": "numpy",
    "torch": "torch",
    "torchaudio": "torchaudio",
    "transformers": "transformers",
    "pygame": "pygame",
    "soundfile": "soundfile",
    "colorama": "colorama",
    "pygments": "Pygments",
    "rapidfuzz": "rapidfuzz",
    "psutil": "psutil",
    "playwright": "playwright",
    "ddgs": "ddgs",
    "flask": "Flask",
    "multipart": "python-multipart",
    "jwt": "PyJWT",
    "dateutil": "python-dateutil",
    "pkg_resources": "setuptools",
    "setuptools": "setuptools",
    "google": "google",  # loose; refine if needed
    "TTS": "coqui-tts",
    "coqui_tts": "coqui-tts",
    "defusedxml": "defusedxml",
    "pytest": "pytest",
    "pytest_asyncio": "pytest-asyncio",
    "pytest_cov": "pytest-cov",
    "pytest_mock": "pytest-mock",
    "serial": "pyserial",
    "websocket": "websocket-client",
    "websockets": "websockets",
    "redis": "redis",
    "celery": "celery",
    "boto3": "boto3",
    "botocore": "botocore",
    "gi": "PyGObject",
    "cv2": "opencv-python",
}

# Test-only / CI tooling — reported as optional unless declared
OPTIONAL_IMPORTS: Set[str] = {
    "pytest",
    "pytest_asyncio",
    "pytest_cov",
    "pytest_mock",
    "_pytest",
    "yaml",  # often only docker-config tests
    "coverage",
    "mypy",
    "ruff",
    "black",
    "isort",
    "hypothesis",
    "freezegun",
    "responses",
    "respx",
}

# Always treat as optional (dynamic / heavy / env-specific)
DYNAMIC_OPTIONAL: Set[str] = {
    "torch",
    "torchaudio",
    "TTS",
    "transformers",
    "onnxruntime",
    "rapidocr",
    "rapidocr_onnxruntime",  # legacy import path; code prefers `rapidocr`
    "playwright",  # browsers installed separately
    "sentence_transformers",  # OpenWebUI host function, not Memory server image
    "sklearn",
    "pyautogui",  # jank local controller, not container API path
}

# Filenames whose third-party imports are host/plugin/jank-only (not the module image)
HOST_ONLY_FILE_NAMES: Set[str] = {
    "function-adaptive_memory_v4.py",
    "rapid_ocr_de.py",
    "jank_controller.py",
    "jank_scraper.js",
}

SKIP_DIR_NAMES: Set[str] = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "Not Maintained",
    "dist",
    "build",
    ".tox",
    "gallery",
    "test_frames",
    "cache",
    "backups",
    "exports",
    "logs",
}

# Modules known to ship Python but no requirements.txt yet
EXTRA_MODULE_ROOTS = [
    "finja-chat",
    "Finja-music/finja-everything-in-once",
]

REQ_LINE_RE = re.compile(
    r"""^\s*
    ([A-Za-z0-9][A-Za-z0-9._\-]*)
    """,
    re.VERBOSE,
)

EXTRAS_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)\s*\[")


def normalize_dist(name: str) -> str:
    """PEP 503-ish normalize for comparison."""
    return re.sub(r"[-_.]+", "-", name).lower()


def stdlib_names() -> Set[str]:
    names = set(getattr(sys, "stdlib_module_names", set()))
    # Always keep common ones even on odd runtimes
    names.update(
        {
            "os",
            "sys",
            "re",
            "json",
            "ast",
            "pathlib",
            "typing",
            "collections",
            "functools",
            "itertools",
            "subprocess",
            "threading",
            "asyncio",
            "logging",
            "argparse",
            "dataclasses",
            "datetime",
            "time",
            "math",
            "hashlib",
            "base64",
            "copy",
            "enum",
            "uuid",
            "tempfile",
            "shutil",
            "glob",
            "io",
            "csv",
            "sqlite3",
            "http",
            "urllib",
            "email",
            "html",
            "xml",
            "socket",
            "ssl",
            "struct",
            "queue",
            "multiprocessing",
            "concurrent",
            "contextlib",
            "traceback",
            "warnings",
            "inspect",
            "importlib",
            "pkgutil",
            "platform",
            "signal",
            "secrets",
            "string",
            "textwrap",
            "unittest",
            "types",
            "abc",
            "weakref",
            "pprint",
            "difflib",
            "fnmatch",
            "stat",
            "errno",
            "ctypes",
            "gzip",
            "zipfile",
            "tarfile",
            "configparser",
            "tomllib",
            "zoneinfo",
            "graphlib",
            "bisect",
            "heapq",
            "array",
            "mmap",
            "select",
            "selectors",
            "ipaddress",
            "numbers",
            "decimal",
            "fractions",
            "random",
            "statistics",
            "operator",
            "keyword",
            "token",
            "tokenize",
            "linecache",
            "dis",
            "pickle",
            "shelve",
            "dbm",
            "codecs",
            "unicodedata",
            "locale",
            "gettext",
            "calendar",
            "cgi",
            "cgitb",
            "wsgiref",
            "xmlrpc",
            "webbrowser",
            "cmd",
            "shlex",
            "tkinter",
            "turtle",
            "pydoc",
            "doctest",
            "pdb",
            "profile",
            "cProfile",
            "timeit",
            "trace",
            "gc",
            "sysconfig",
            "builtins",
            "__future__",
        }
    )
    return names


STDLIB = stdlib_names()

# If the parent dist is declared, treat these as covered (common FastAPI stack).
IMPLIED_BY_PARENT: Dict[str, Set[str]] = {
    normalize_dist("fastapi"): {
        normalize_dist(x)
        for x in ("pydantic", "starlette", "anyio", "typing-extensions", "annotated-types")
    },
    normalize_dist("uvicorn"): {normalize_dist(x) for x in ("h11", "click", "httptools", "uvloop", "watchfiles", "websockets")},
    normalize_dist("requests"): {
        normalize_dist(x)
        for x in ("urllib3", "certifi", "charset-normalizer", "idna")
    },
    normalize_dist("rapidocr"): {
        normalize_dist(x) for x in ("onnxruntime", "numpy", "opencv-python", "pyclipper", "shapely")
    },
    normalize_dist("coqui-tts"): {
        normalize_dist(x) for x in ("torch", "torchaudio", "transformers", "numpy")
    },
}


def is_covered(norm: str, declared: Set[str]) -> bool:
    if norm in declared:
        return True
    for parent, children in IMPLIED_BY_PARENT.items():
        if parent in declared and norm in children:
            return True
    return False


@dataclass
class ModuleReport:
    path: str
    requirements_files: List[str] = field(default_factory=list)
    declared: Set[str] = field(default_factory=set)  # normalized dist names
    declared_raw: Dict[str, str] = field(default_factory=dict)  # norm -> display
    used_imports: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    # import_name -> set of relative file paths
    local_top_levels: Set[str] = field(default_factory=set)
    ok: List[Tuple[str, str]] = field(default_factory=list)  # (import, dist)
    missing: List[Tuple[str, str, List[str]]] = field(default_factory=list)
    optional: List[Tuple[str, str, List[str]]] = field(default_factory=list)
    local: List[Tuple[str, List[str]]] = field(default_factory=list)
    unused: List[str] = field(default_factory=list)
    dynamic: List[Tuple[str, str, List[str]]] = field(default_factory=list)


def should_skip_dir(path: Path) -> bool:
    return path.name in SKIP_DIR_NAMES


def discover_module_roots(repo: Path) -> List[Path]:
    roots: List[Path] = []
    seen: Set[Path] = set()

    for req in repo.rglob("requirements.txt"):
        if any(part in SKIP_DIR_NAMES for part in req.parts):
            continue
        root = req.parent.resolve()
        if root not in seen:
            seen.add(root)
            roots.append(root)

    for req in repo.rglob("requirements.in"):
        if any(part in SKIP_DIR_NAMES for part in req.parts):
            continue
        root = req.parent.resolve()
        if root not in seen:
            seen.add(root)
            roots.append(root)

    for rel in EXTRA_MODULE_ROOTS:
        p = (repo / rel).resolve()
        if p.is_dir() and p not in seen:
            seen.add(p)
            roots.append(p)

    # Prefer deeper roots first when assigning files (handled per-module scan)
    roots.sort(key=lambda p: len(p.parts), reverse=True)
    return roots


def parse_requirement_name(line: str) -> Optional[str]:
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return None
    # env markers
    line = line.split(";", 1)[0].strip()
    m = EXTRAS_RE.match(line)
    if m:
        return m.group(1)
    # strip version operators
    for sep in ("===", "==", ">=", "<=", "~=", "!=", ">", "<"):
        if sep in line:
            line = line.split(sep, 1)[0].strip()
            break
    # extras after name: package[extra]
    if "[" in line:
        line = line.split("[", 1)[0].strip()
    m = REQ_LINE_RE.match(line)
    if not m:
        return None
    return m.group(1)


def load_declared(module_root: Path) -> Tuple[Set[str], Dict[str, str], List[str]]:
    """Return normalized declared set, display map, and file list."""
    declared: Set[str] = set()
    display: Dict[str, str] = {}
    files: List[str] = []

    candidates = list(module_root.glob("requirements*.txt")) + list(
        module_root.glob("requirements*.in")
    )
    pyproject = module_root / "pyproject.toml"
    if pyproject.is_file():
        candidates.append(pyproject)

    for path in sorted(set(candidates)):
        files.append(str(path))
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "pyproject.toml":
            # Minimal parse: dependencies = [ "foo>=1", ... ]
            for m in re.finditer(
                r'["\']([A-Za-z0-9][A-Za-z0-9._\-]*)[A-Za-z0-9._\-\[\]<>=!~,.\s]*["\']',
                text,
            ):
                # Only take lines that look like deps blocks — coarse but useful
                pass
            # Better: grab dependency arrays
            for block in re.finditer(
                r"(?:dependencies|requires)\s*=\s*\[(.*?)\]",
                text,
                re.DOTALL | re.IGNORECASE,
            ):
                for item in re.findall(r'["\']([^"\']+)["\']', block.group(1)):
                    name = parse_requirement_name(item)
                    if name:
                        n = normalize_dist(name)
                        declared.add(n)
                        display[n] = name
            continue

        for raw in text.splitlines():
            name = parse_requirement_name(raw)
            if name:
                n = normalize_dist(name)
                declared.add(n)
                display[n] = name

    return declared, display, files


def local_top_levels(module_root: Path) -> Set[str]:
    """Importable names that live inside this module root.

    Finja modules often put packages on sys.path (e.g. `from brain import …`
    while brain.py sits under core/). Treat any .py stem or package directory
    under the module as local so we do not demand PyPI packages for them.
    """
    names: Set[str] = set()
    for py in module_root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in py.parts):
            continue
        names.add(py.stem)
        try:
            rel = py.relative_to(module_root)
        except ValueError:
            continue
        for part in rel.parts[:-1]:
            if part not in SKIP_DIR_NAMES:
                names.add(part)
                names.add(part.replace("-", "_"))
    for directory in module_root.rglob("*"):
        if not directory.is_dir() or should_skip_dir(directory):
            continue
        if any(part in SKIP_DIR_NAMES for part in directory.parts):
            continue
        names.add(directory.name)
        names.add(directory.name.replace("-", "_"))
    names.add(module_root.name.replace("-", "_"))
    return names


def extract_imports(py_path: Path) -> Tuple[Set[str], Set[str]]:
    """Return (static_top_levels, dynamic_hints)."""
    static: Set[str] = set()
    dynamic: Set[str] = set()
    try:
        src = py_path.read_text(encoding="utf-8-sig", errors="replace")  # strip BOM
    except OSError:
        return static, dynamic

    try:
        tree = ast.parse(src, filename=str(py_path))
    except SyntaxError:
        return static, dynamic

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                static.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level and not node.module:
                continue  # relative
            if node.module:
                if node.level:
                    # from .foo import bar — local
                    continue
                top = node.module.split(".", 1)[0]
                static.add(top)
        elif isinstance(node, ast.Call):
            # __import__("x") / importlib.import_module("x")
            func = node.func
            name = None
            if isinstance(func, ast.Name) and func.id == "__import__":
                name = "direct"
            elif isinstance(func, ast.Attribute) and func.attr == "import_module":
                name = "import_module"
            if name and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    dynamic.add(arg0.value.split(".", 1)[0])

    return static, dynamic


def is_test_file(path: Path) -> bool:
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in {"tests", "test"} for part in path.parts)


def dist_for_import(import_name: str) -> str:
    if import_name in IMPORT_TO_DIST:
        return IMPORT_TO_DIST[import_name]
    return import_name.replace("_", "-")


def analyze_module(module_root: Path, repo: Path) -> ModuleReport:
    rel_root = str(module_root.relative_to(repo)) if module_root.is_relative_to(repo) else str(module_root)
    report = ModuleReport(path=rel_root)
    declared, display, files = load_declared(module_root)
    report.declared = declared
    report.declared_raw = display
    report.requirements_files = [str(Path(f).relative_to(repo)) if Path(f).is_relative_to(repo) else f for f in files]
    report.local_top_levels = local_top_levels(module_root)

    used_static: Dict[str, Set[str]] = defaultdict(set)
    used_dynamic: Dict[str, Set[str]] = defaultdict(set)

    for py in module_root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in py.parts):
            continue
        # Don't dive into nested modules that have their own requirements
        try:
            rel = py.relative_to(module_root)
        except ValueError:
            continue
        # skip nested req roots
        skip = False
        for parent in [module_root / p for p in rel.parts[:-1]]:
            if parent != module_root and (
                (parent / "requirements.txt").is_file()
                or (parent / "requirements.in").is_file()
            ):
                skip = True
                break
        if skip:
            continue

        static, dynamic = extract_imports(py)
        try:
            rel_s = str(py.relative_to(repo))
        except ValueError:
            rel_s = str(py)
        for name in static:
            used_static[name].add(rel_s)
        for name in dynamic:
            used_dynamic[name].add(rel_s)

    report.used_imports = used_static

    used_dists: Set[str] = set()

    all_names = set(used_static) | set(used_dynamic)
    for import_name in sorted(all_names):
        files_hit = sorted(used_static.get(import_name, set()) | used_dynamic.get(import_name, set()))
        is_dyn = import_name in used_dynamic and import_name not in used_static

        if import_name in STDLIB or import_name.startswith("_"):
            continue
        if import_name in report.local_top_levels:
            report.local.append((import_name, files_hit))
            continue

        dist = dist_for_import(import_name)
        norm = normalize_dist(dist)
        used_dists.add(norm)

        only_tests = bool(files_hit) and all(is_test_file(Path(f)) for f in files_hit)
        only_host = bool(files_hit) and all(
            Path(f).name in HOST_ONLY_FILE_NAMES for f in files_hit
        )
        is_dynamic_opt = (
            import_name in DYNAMIC_OPTIONAL
            or normalize_dist(import_name)
            in {normalize_dist(x) for x in DYNAMIC_OPTIONAL}
        )
        optionalish = (
            import_name in OPTIONAL_IMPORTS
            or is_dynamic_opt
            or only_tests
            or only_host
            or is_dyn
        )

        if is_covered(norm, declared) or is_covered(normalize_dist(import_name), declared):
            report.ok.append((import_name, display.get(norm, dist)))
        elif optionalish:
            if is_dynamic_opt or is_dyn:
                report.dynamic.append((import_name, dist, files_hit))
            else:
                report.optional.append((import_name, dist, files_hit))
        else:
            report.missing.append((import_name, dist, files_hit))

    # Declared but never imported (coarse — transitive / CLI-only may false-positive).
    # Skip common FastAPI/runtime packages and *reverse* IMPLIED_BY_PARENT:
    # e.g. onnxruntime is declared for rapidocr; python-multipart for UploadFile.
    TRANSITIVE_OK = {
        normalize_dist(x)
        for x in (
            "starlette",
            "uvicorn",
            "urllib3",
            "anyio",
            "sniffio",
            "idna",
            "certifi",
            "charset-normalizer",
            "h11",
            "click",
            "typing-extensions",
            "annotated-types",
            "pydantic-core",
            # FastAPI needs this package installed; apps rarely `import multipart`
            "python-multipart",
            # Starlette/FastAPI TestClient needs httpx even without `import httpx`
            "httpx",
            # pytest plugins often have no import of the dist name
            "pytest-asyncio",
            "pytest-cov",
            "pytest-mock",
        )
    }
    # If parent dist is used OR declared, children are not "unused noise"
    implied_children_covered: Set[str] = set()
    for parent, children in IMPLIED_BY_PARENT.items():
        if parent in used_dists or parent in declared:
            implied_children_covered |= children

    for n in sorted(declared):
        if n in used_dists or n in TRANSITIVE_OK or n in implied_children_covered:
            continue
        report.unused.append(display.get(n, n))

    return report


def print_report(reports: List[ModuleReport], strict: bool) -> int:
    missing_total = 0
    unused_total = 0

    for r in reports:
        print()
        print("=" * 72)
        print(f"📦 {r.path}")
        if r.requirements_files:
            print(f"   manifests: {', '.join(r.requirements_files)}")
        else:
            print("   manifests: ⚠️  none (no requirements*.txt / .in / pyproject)")
        print("-" * 72)

        if r.ok:
            print(f"  ✅ used + declared ({len(r.ok)})")
            for imp, dist in r.ok[:30]:
                print(f"      {imp} → {dist}")
            if len(r.ok) > 30:
                print(f"      … +{len(r.ok) - 30} more")

        if r.local:
            print(f"  📁 local Finja / module code ({len(r.local)})")
            for imp, files in r.local[:15]:
                print(f"      {imp}")
            if len(r.local) > 15:
                print(f"      … +{len(r.local) - 15} more")

        if r.optional:
            print(f"  ⚠️  optional / test-only ({len(r.optional)})")
            for imp, dist, files in r.optional:
                sample = files[0] if files else "?"
                print(f"      {imp} → {dist}  ({sample})")

        if r.dynamic:
            print(f"  ⚠️  dynamic / heavy optional ({len(r.dynamic)})")
            for imp, dist, files in r.dynamic:
                print(f"      {imp} → {dist}")

        if r.missing:
            print(f"  ❌ used, but missing from requirements ({len(r.missing)})")
            for imp, dist, files in r.missing:
                sample = ", ".join(files[:2])
                print(f"      {imp} → add `{dist}`  [{sample}]")
            missing_total += len(r.missing)

        if r.unused:
            print(f"  🗑️  declared, but import not found ({len(r.unused)})")
            for dist in r.unused:
                print(f"      {dist}")
            unused_total += len(r.unused)

        if not (r.ok or r.missing or r.optional or r.dynamic or r.local):
            print("  (no external imports detected)")

    print()
    print("=" * 72)
    print(
        f"Summary: {missing_total} missing, {unused_total} unused-declared "
        f"across {len(reports)} module roots"
    )
    if missing_total:
        print("Result: FAIL (undeclared third-party imports)")
        return 1
    if strict and unused_total:
        print("Result: FAIL (--strict: unused declarations)")
        return 1
    print("Result: OK")
    return 0


def reports_to_json(reports: List[ModuleReport]) -> list:
    out = []
    for r in reports:
        out.append(
            {
                "path": r.path,
                "requirements_files": r.requirements_files,
                "ok": [{"import": i, "dist": d} for i, d in r.ok],
                "missing": [
                    {"import": i, "dist": d, "files": f} for i, d, f in r.missing
                ],
                "optional": [
                    {"import": i, "dist": d, "files": f} for i, d, f in r.optional
                ],
                "dynamic": [
                    {"import": i, "dist": d, "files": f} for i, d, f in r.dynamic
                ],
                "local": [{"import": i, "files": f} for i, f in r.local],
                "unused_declared": r.unused,
            }
        )
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Finja dependency guard")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: parent of tools/)",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help="Only scan this relative module path (repeatable)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail when requirements list unused packages",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print findings but always exit 0 (useful while paying down debt)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Write machine-readable report to this path",
    )
    args = parser.parse_args(argv)

    if args.root:
        repo = args.root.resolve()
    else:
        repo = Path(__file__).resolve().parent.parent

    if not repo.is_dir():
        print(f"Not a directory: {repo}", file=sys.stderr)
        return 2

    roots = discover_module_roots(repo)
    if args.module:
        wanted = {(repo / m).resolve() for m in args.module}
        roots = [r for r in roots if r in wanted or any(r.is_relative_to(w) for w in wanted for r in [r])]
        # also allow exact path match by string
        if not roots:
            roots = []
            for m in args.module:
                p = (repo / m).resolve()
                if p.is_dir():
                    roots.append(p)

    if not roots:
        print("No module roots found.", file=sys.stderr)
        return 2

    # de-dupe while keeping deeper first then stable path sort for display
    unique = []
    seen = set()
    for r in sorted(roots, key=lambda p: str(p)):
        if r not in seen:
            seen.add(r)
            unique.append(r)

    reports = [analyze_module(r, repo) for r in unique]

    if args.json:
        args.json.write_text(
            json.dumps(reports_to_json(reports), indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {args.json}")

    code = print_report(reports, strict=args.strict)
    if args.warn_only and code == 1:
        print("(--warn-only: not failing the process)")
        return 0
    return code


if __name__ == "__main__":
    raise SystemExit(main())
