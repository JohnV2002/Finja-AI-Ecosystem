"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/registry.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Dynamic project registry (paths, prefix, parent/module modes).

  New in v1.0.0:
    • Production release packaging for public GitHub
    • Cross-project engine, ambient hooks, global code ledger
    • See repository README.md / INSTALL.md / AMBIENT.md

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SEED_REGISTRY = PLUGIN_ROOT / "registry" / "projects.json"

MODE_OWN = "own_prefix"
MODE_INHERIT = "inherit_parent"
MODE_MODULE = "module_under_parent"
VALID_MODES = {MODE_OWN, MODE_INHERIT, MODE_MODULE}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_user_registry_path() -> Path:
    home = os.environ.get("ERROR_CONTRACT_HOME")
    if home:
        return Path(home).expanduser() / "projects.json"
    return Path.home() / ".error_contract" / "projects.json"


def registry_paths() -> list[Path]:
    """Ordered paths used for load (later entries only fill gaps / merge by id)."""
    paths: list[Path] = []
    user = default_user_registry_path()
    paths.append(user)
    if SEED_REGISTRY.is_file():
        paths.append(SEED_REGISTRY)
    extra = os.environ.get("ERROR_CONTRACT_REGISTRY")
    if extra:
        paths.insert(0, Path(extra).expanduser())
    # unique preserve order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def write_registry_path() -> Path:
    """Where new registrations are persisted (user-global by default)."""
    override = os.environ.get("ERROR_CONTRACT_REGISTRY")
    if override:
        return Path(override).expanduser()
    return default_user_registry_path()


def _norm_path(p: str | Path) -> str:
    try:
        return str(Path(p).expanduser().resolve()).replace("\\", "/").lower()
    except OSError:
        return str(p).replace("\\", "/").lower()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    s = s.strip("-")
    return s[:64] or f"project-{uuid.uuid4().hex[:8]}"


def suggest_prefix(name: str) -> str:
    """Heuristic only - never auto-commit without user/agent confirm."""
    tokens = re.findall(r"[A-Za-z0-9]+", name)
    if not tokens:
        return "APP"
    # Prefer first meaningful token, max 8 chars
    t = tokens[0].upper()
    if t in {"THE", "MY", "NEW", "TEST"} and len(tokens) > 1:
        t = tokens[1].upper()
    return t[:12]


@dataclass
class ProjectEntry:
    id: str
    name: str
    prefix: str
    mode: str = MODE_OWN
    paths: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    ecosystem: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    module_default: str = ""
    exceptions_rel: str = "core/exceptions.py"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def effective_prefix(self, registry: "Registry") -> str:
        if self.mode == MODE_OWN:
            return self.prefix.upper()
        if self.mode in {MODE_INHERIT, MODE_MODULE} and self.parent_id:
            parent = registry.by_id(self.parent_id)
            if parent:
                return parent.effective_prefix(registry)
        return self.prefix.upper()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectEntry":
        return cls(
            id=str(data.get("id") or _slug(str(data.get("name") or "project"))),
            name=str(data.get("name") or data.get("id") or "unnamed"),
            prefix=str(data.get("prefix") or "APP").strip().upper(),
            mode=str(data.get("mode") or MODE_OWN),
            paths=[str(p) for p in (data.get("paths") or [])],
            parent_id=data.get("parent_id"),
            ecosystem=list(data.get("ecosystem") or []),
            owners=list(data.get("owners") or []),
            tags=list(data.get("tags") or []),
            module_default=str(data.get("module_default") or ""),
            exceptions_rel=str(data.get("exceptions_rel") or "core/exceptions.py"),
            notes=str(data.get("notes") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class Registry:
    projects: list[ProjectEntry] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def by_id(self, project_id: str) -> Optional[ProjectEntry]:
        for p in self.projects:
            if p.id == project_id:
                return p
        return None

    def all_prefixes(self) -> list[str]:
        return sorted({p.prefix.upper() for p in self.projects if p.prefix})

    def parents(self) -> list[ProjectEntry]:
        """Projects that can act as parents (own_prefix roots, or anything)."""
        return [p for p in self.projects if p.mode == MODE_OWN or not p.parent_id]

    def match_path(self, path: str | Path) -> Optional[ProjectEntry]:
        target = _norm_path(path)
        # Longest path match wins (nested roots)
        best: Optional[ProjectEntry] = None
        best_len = -1
        for proj in self.projects:
            for raw in proj.paths:
                n = _norm_path(raw)
                if target == n or target.startswith(n.rstrip("/") + "/"):
                    if len(n) > best_len:
                        best = proj
                        best_len = len(n)
        return best

    def upsert(self, entry: ProjectEntry) -> ProjectEntry:
        now = _utc_now()
        existing = self.by_id(entry.id)
        if existing:
            entry.created_at = existing.created_at or now
            entry.updated_at = now
            self.projects = [entry if p.id == entry.id else p for p in self.projects]
        else:
            entry.created_at = entry.created_at or now
            entry.updated_at = now
            self.projects.append(entry)
        return entry

    def remove(self, project_id: str) -> bool:
        before = len(self.projects)
        self.projects = [p for p in self.projects if p.id != project_id]
        return len(self.projects) < before

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": _utc_now(),
            "projects": [p.to_dict() for p in sorted(self.projects, key=lambda x: x.id)],
        }


def load_registry() -> Registry:
    reg = Registry()
    by_id: dict[str, ProjectEntry] = {}
    for path in registry_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        reg.sources.append(str(path))
        for raw in data.get("projects") or []:
            if not isinstance(raw, dict):
                continue
            entry = ProjectEntry.from_dict(raw)
            # First file in list is primary (user); seed fills missing ids only
            if entry.id not in by_id:
                by_id[entry.id] = entry
    reg.projects = list(by_id.values())
    return reg


def save_registry(reg: Registry, path: Optional[Path] = None) -> Path:
    path = path or write_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def resolve_project(path: str | Path, reg: Optional[Registry] = None) -> dict[str, Any]:
    """Resolve path -> registry entry + effective prefix, or needs_onboard payload."""
    reg = reg or load_registry()
    root = Path(path).expanduser().resolve()
    hit = reg.match_path(root)
    if hit:
        return {
            "status": "known",
            "path": str(root),
            "project": hit.to_dict(),
            "effective_prefix": hit.effective_prefix(reg),
            "registry_sources": reg.sources,
        }

    name = root.name
    suggested_id = _slug(name)
    suggested_prefix = suggest_prefix(name)
    parents = [
        {
            "id": p.id,
            "name": p.name,
            "prefix": p.effective_prefix(reg),
            "ecosystem": p.ecosystem,
            "owners": p.owners,
        }
        for p in reg.parents()
    ]
    return {
        "status": "needs_onboard",
        "path": str(root),
        "suggested_id": suggested_id,
        "suggested_name": name,
        "suggested_prefix": suggested_prefix,
        "known_prefixes": reg.all_prefixes(),
        "candidate_parents": parents,
        "modes": [
            {
                "id": MODE_OWN,
                "label": "Own prefix",
                "meaning": f"Errors branded {suggested_prefix}-xxx (or your choice). Independent brand.",
            },
            {
                "id": MODE_INHERIT,
                "label": "Inherit parent prefix",
                "meaning": "Same codes as parent (e.g. FINJA-xxx) even if folder is separate.",
            },
            {
                "id": MODE_MODULE,
                "label": "Parent prefix + module tag",
                "meaning": "Parent codes (FINJA-xxx) but default module=this-project (e.g. omni).",
            },
        ],
        "questions": onboard_questions(
            suggested_name=name,
            suggested_prefix=suggested_prefix,
            parents=parents,
        ),
        "ai_instruction": (
            "STOP coding errors. Ask the human the questions below. "
            "Then run: python -m error_contract register <path> --id ... --prefix ... --mode ... "
            "[--parent-id ...] [--ecosystem ...] [--owners ...] [--module-default ...] "
            "Then: python -m error_contract ensure <path>"
        ),
        "registry_sources": reg.sources,
    }


def onboard_questions(
    *,
    suggested_name: str,
    suggested_prefix: str,
    parents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parent_opts = [
        {"id": p["id"], "label": f"{p['name']} ({p['prefix']})", "description": f"owners={p.get('owners')} eco={p.get('ecosystem')}"}
        for p in parents
    ] or [{"id": "_none", "label": "No parents registered yet", "description": "Register Finja first if needed"}]

    return [
        {
            "id": "mode",
            "prompt": (
                f"Neues Projekt «{suggested_name}»: eigene Error-Codes "
                f"({suggested_prefix}-xxx), unter einem Parent (z.B. FINJA-xxx), "
                f"oder Parent-Codes + module-Tag? "
                f"(Beispiel Omni: Finja-Stack, aber VPet-Welt - oft module_under_parent "
                f"oder own_prefix OMNI, owners=vpet, ecosystem=finja.)"
            ),
            "options": [
                {"id": MODE_OWN, "label": f"Eigener Prefix ({suggested_prefix} oder custom)"},
                {"id": MODE_INHERIT, "label": "Parent-Prefix erben (gleiche Codes)"},
                {"id": MODE_MODULE, "label": "Parent-Prefix + module=projekt"},
            ],
        },
        {
            "id": "prefix",
            "prompt": f"Welcher Prefix? (Vorschlag: {suggested_prefix}. Bei inherit/module: Parent-Prefix.)",
            "options": [
                {"id": suggested_prefix, "label": suggested_prefix},
                {"id": "custom", "label": "Anderer Prefix (tippen)"},
            ],
        },
        {
            "id": "parent_id",
            "prompt": "Falls inherit/module: welcher Parent?",
            "options": parent_opts,
            "skip_if_mode": MODE_OWN,
        },
        {
            "id": "owners",
            "prompt": "Owner / Welt? (frei, komma-getrennt - z.B. finja, vpet, games)",
            "options": [
                {"id": "finja", "label": "finja"},
                {"id": "vpet", "label": "vpet"},
                {"id": "games", "label": "games"},
                {"id": "other", "label": "other (tippen)"},
            ],
            "multi": True,
        },
        {
            "id": "ecosystem",
            "prompt": "Ecosystem-Tags? (z.B. finja auch wenn Owner vpet ist - Omni-Fall)",
            "options": [
                {"id": "finja", "label": "finja"},
                {"id": "vpet", "label": "vpet"},
                {"id": "standalone", "label": "standalone"},
            ],
            "multi": True,
        },
        {
            "id": "module_default",
            "prompt": "Bei mode=module_under_parent: default module string? (z.B. omni)",
            "options": [
                {"id": _slug(suggested_name).replace("-", "_")[:32], "label": "from project name"},
                {"id": "custom", "label": "custom"},
            ],
            "skip_if_mode_not": MODE_MODULE,
        },
    ]


def register_project(
    path: str | Path,
    *,
    project_id: str = "",
    name: str = "",
    prefix: str,
    mode: str = MODE_OWN,
    parent_id: str = "",
    ecosystem: Optional[list[str]] = None,
    owners: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    module_default: str = "",
    notes: str = "",
    exceptions_rel: str = "core/exceptions.py",
    reg: Optional[Registry] = None,
    persist: bool = True,
) -> tuple[ProjectEntry, Path | None]:
    reg = reg or load_registry()
    root = Path(path).expanduser().resolve()
    mode = (mode or MODE_OWN).strip()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode {mode!r}; expected one of {sorted(VALID_MODES)}")

    prefix = prefix.strip().upper()
    if not prefix:
        raise ValueError("prefix required")

    if mode in {MODE_INHERIT, MODE_MODULE}:
        if not parent_id:
            raise ValueError(f"mode={mode} requires --parent-id")
        parent = reg.by_id(parent_id)
        if not parent:
            raise ValueError(f"Unknown parent_id={parent_id!r}. Register parent first.")
        # Align prefix with parent effective brand unless user forces otherwise
        prefix = parent.effective_prefix(reg)

    entry = ProjectEntry(
        id=project_id or _slug(name or root.name),
        name=name or root.name,
        prefix=prefix,
        mode=mode,
        paths=[str(root)],
        parent_id=parent_id or None,
        ecosystem=ecosystem or [],
        owners=owners or [],
        tags=tags or [],
        module_default=module_default if mode == MODE_MODULE else "",
        exceptions_rel=exceptions_rel,
        notes=notes,
    )
    # Merge paths if same id already exists
    existing = reg.by_id(entry.id)
    if existing:
        paths = list(dict.fromkeys([*existing.paths, *entry.paths]))
        entry.paths = paths
        entry.created_at = existing.created_at

    reg.upsert(entry)
    saved: Path | None = None
    if persist:
        saved = save_registry(reg)
    return entry, saved


def format_resolve(result: dict[str, Any]) -> str:
    if result["status"] == "known":
        p = result["project"]
        lines = [
            "=== Project Resolve: KNOWN ===",
            f"Path    : {result['path']}",
            f"Id      : {p['id']}",
            f"Name    : {p['name']}",
            f"Prefix  : {result['effective_prefix']}  (stored={p['prefix']}, mode={p['mode']})",
            f"Parent  : {p.get('parent_id') or '-'}",
            f"Owners  : {', '.join(p.get('owners') or []) or '-'}",
            f"Eco     : {', '.join(p.get('ecosystem') or []) or '-'}",
            f"Module  : {p.get('module_default') or '-'}",
            f"Notes   : {p.get('notes') or '-'}",
        ]
        return "\n".join(lines) + "\n"

    lines = [
        "=== Project Resolve: NEEDS ONBOARD ===",
        f"Path    : {result['path']}",
        f"Suggest : id={result['suggested_id']}  prefix={result['suggested_prefix']}",
        f"Known prefixes: {', '.join(result.get('known_prefixes') or []) or '(none yet)'}",
        "",
        result.get("ai_instruction", ""),
        "",
        "Questions for the human:",
    ]
    for i, q in enumerate(result.get("questions") or [], 1):
        lines.append(f"  Q{i}. [{q['id']}] {q['prompt']}")
        for opt in q.get("options") or []:
            lines.append(f"       - {opt.get('id')}: {opt.get('label')}")
    lines.append("")
    lines.append("After answers:")
    lines.append(
        "  python -m error_contract register PATH --id ID --prefix PREF "
        "--mode own_prefix|inherit_parent|module_under_parent "
        "[--parent-id PID] [--owners a,b] [--ecosystem a,b] [--module-default m]"
    )
    lines.append("  python -m error_contract ensure PATH")
    return "\n".join(lines) + "\n"


def format_registry_list(reg: Registry) -> str:
    if not reg.projects:
        return "Registry empty. Seed Finja with: python -m error_contract register <finja-path> --id finja --prefix FINJA --mode own_prefix --owners finja --ecosystem finja\n"
    lines = [
        f"Projects: {len(reg.projects)}  sources: {', '.join(reg.sources) or write_registry_path()}",
        f"{'ID':<28} {'PREFIX':<10} {'MODE':<20} {'PARENT':<16} NAME",
        "-" * 90,
    ]
    for p in sorted(reg.projects, key=lambda x: x.id):
        lines.append(
            f"{p.id:<28} {p.effective_prefix(reg):<10} {p.mode:<20} {(p.parent_id or '-'):<16} {p.name}"
        )
    return "\n".join(lines) + "\n"
