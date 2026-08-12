"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/ledger.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Global prefix code ledger -- unique FINJA-xxx numbers across owners.

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
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import DEFAULT_BANDS
from .taxonomy import (
    band_for_num,
    finja_reference_taxonomy,
    parse_exceptions_py,
    suggest_class_name,
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_ledger_path() -> Path:
    import os

    home = os.environ.get("ERROR_CONTRACT_HOME")
    if home:
        return Path(home).expanduser() / "code_ledger.json"
    return Path.home() / ".error_contract" / "code_ledger.json"


def repository_root(path: str | Path) -> Path:
    """Return the containing Git root, or the supplied project root."""
    start = Path(path).expanduser().resolve()
    start = start.parent if start.is_file() else start
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def canonical_registry_path(prefix: str, project_root: str | Path = ".") -> Path:
    """Public, human-findable legend at the repository root."""
    del prefix  # one root legend may contain several independent namespaces
    return repository_root(project_root) / "error_contract.json"


def load_namespace_ledger(prefix: str, project_root: str | Path = ".") -> "CodeLedger":
    """Load the public repo-root legend, creating its in-memory shape if absent."""
    path = canonical_registry_path(prefix, project_root)
    ledger = load_ledger(path)
    ledger.public_legend_schema = True
    return ledger


@dataclass
class CodeClaim:
    code_num: int
    class_name: str
    band: str
    prefix: str
    owner_id: str = ""  # project registry id: finja, finja-chat, ...
    module: str = ""  # runtime module= tag
    description: str = ""
    source_path: str = ""  # exceptions file if any; empty = registry-only
    base_class: str = "AppError"
    to_inbox: bool = True
    created_at: str = ""
    updated_at: str = ""

    def branded(self) -> str:
        return f"{self.prefix.upper()}-{self.code_num}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], prefix: str = "") -> "CodeClaim":
        return cls(
            code_num=int(data["code_num"]),
            class_name=str(data.get("class_name") or f"Error{data.get('code_num')}"),
            band=str(data.get("band") or band_for_num(int(data["code_num"]))),
            prefix=str(data.get("prefix") or prefix or "APP").upper(),
            owner_id=str(data.get("owner_id") or ""),
            module=str(data.get("module") or ""),
            description=str(data.get("description") or data.get("message_hint") or ""),
            source_path=str(data.get("source_path") or ""),
            base_class=str(data.get("base_class") or "AppError"),
            to_inbox=bool(data.get("to_inbox", True)),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class CodeLedger:
    """All prefixes in one file; each prefix is its own number space."""

    path: Path = field(default_factory=default_ledger_path)
    # prefix -> code_num(str) -> claim
    prefixes: dict[str, dict[str, CodeClaim]] = field(default_factory=dict)
    version: int = 1
    namespace_schema: bool = False
    namespace: str = ""
    public_legend_schema: bool = False
    categories: dict[str, dict[str, tuple[int, int, str]]] = field(default_factory=dict)

    def categories_for(self, prefix: str) -> dict[str, tuple[int, int, str]]:
        prefix = prefix.upper()
        if prefix not in self.categories:
            self.categories[prefix] = dict(DEFAULT_BANDS)
        return self.categories[prefix]

    def add_category(
        self,
        prefix: str,
        name: str,
        lo: int,
        hi: int,
        description: str = "",
        *,
        force: bool = False,
    ) -> None:
        prefix = prefix.upper()
        name = name.strip().lower().replace("-", "_")
        if not name or lo < 0 or hi < lo:
            raise ValueError("Category requires a name and a valid ascending numeric range")
        categories = self.categories_for(prefix)
        existing = categories.get(name)
        if existing and existing != (lo, hi, description) and not force:
            raise ValueError(f"Category '{name}' already uses {existing[0]}-{existing[1]}")
        for other, (other_lo, other_hi, _) in categories.items():
            if other == name:
                continue
            if max(lo, other_lo) <= min(hi, other_hi) and not force:
                raise ValueError(
                    f"Range {lo}-{hi} overlaps category '{other}' ({other_lo}-{other_hi})"
                )
        categories[name] = (lo, hi, description or name.replace("_", " ").title())
        self.prefixes.setdefault(prefix, {})

    def claims_for(self, prefix: str) -> dict[int, CodeClaim]:
        p = prefix.upper()
        raw = self.prefixes.get(p) or {}
        return {int(k): v for k, v in raw.items()}

    def get(self, prefix: str, code_num: int) -> Optional[CodeClaim]:
        return self.claims_for(prefix).get(code_num)

    def used_nums(self, prefix: str) -> set[int]:
        return set(self.claims_for(prefix).keys())

    def next_free(self, prefix: str, band: str, extra_used: Optional[set[int]] = None) -> Optional[int]:
        band = band.lower().strip()
        aliases = {
            "auth": "session",
            "guard": "pipeline",
            "safety": "pipeline",
            "system": "host",
            "generic": "unexpected",
            "tools": "tool",
            "plugins": "tool",
            "obs": "tool",
            "twitch": "session",
            "chat": "session",
        }
        band = aliases.get(band, band)
        categories = self.categories_for(prefix)
        if band not in categories:
            return None
        lo, hi, _ = categories[band]
        used = self.used_nums(prefix) | (extra_used or set())
        for n in range(lo, hi + 1):
            if n not in used:
                return n
        return None

    def upsert(self, claim: CodeClaim, *, force: bool = False) -> CodeClaim:
        p = claim.prefix.upper()
        claim.prefix = p
        self.prefixes.setdefault(p, {})
        key = str(claim.code_num)
        existing = self.prefixes[p].get(key)
        now = _utc()
        if existing and not force:
            if existing.owner_id and claim.owner_id and existing.owner_id != claim.owner_id:
                raise ValueError(
                    f"Conflict: {claim.branded()} already owned by '{existing.owner_id}' "
                    f"({existing.class_name}) - cannot assign to '{claim.owner_id}'. "
                    f"Pick another number or use --force (dangerous)."
                )
            if (
                existing.class_name != claim.class_name
                and existing.owner_id
                and existing.owner_id != claim.owner_id
            ):
                raise ValueError(
                    f"Conflict: {claim.branded()} is {existing.class_name} "
                    f"(owner={existing.owner_id}), not {claim.class_name}"
                )
            # same owner refresh
            claim.created_at = existing.created_at or now
        else:
            claim.created_at = claim.created_at or now
        claim.updated_at = now
        self.prefixes[p][key] = claim
        return claim

    def list_claims(self, prefix: str = "") -> list[CodeClaim]:
        if prefix:
            return sorted(self.claims_for(prefix).values(), key=lambda c: c.code_num)
        out: list[CodeClaim] = []
        for p in sorted(self.prefixes.keys()):
            out.extend(sorted(self.claims_for(p).values(), key=lambda c: c.code_num))
        return out

    def to_dict(self) -> dict[str, Any]:
        if self.public_legend_schema:
            return {
                "schema_version": 1,
                "title": "Error Code Legend",
                "updated_at": _utc(),
                "description": (
                    "Public source of truth for every structured error code in this repository. "
                    "Runtime implementations may remain module-local."
                ),
                "namespaces": {
                    prefix: {
                        "categories": {
                            name: {"range": f"{lo}-{hi}", "description": description}
                            for name, (lo, hi, description) in self.categories_for(prefix).items()
                        },
                        "codes": {
                            str(c.code_num): {
                                "name": c.class_name,
                                "owner": c.owner_id,
                                "module": c.module,
                                "category": c.band,
                                "description": c.description,
                                "source": c.source_path,
                                "base_class": c.base_class,
                                "to_inbox": c.to_inbox,
                                "introduced": c.created_at,
                                "updated_at": c.updated_at,
                            }
                            for c in sorted(self.claims_for(prefix).values(), key=lambda item: item.code_num)
                        },
                    }
                    for prefix in sorted(self.prefixes)
                },
            }
        if self.namespace_schema:
            prefix = self.namespace.upper()
            return {
                "namespace": prefix,
                "schema_version": 1,
                "updated_at": _utc(),
                "description": "Canonical namespace registry. Runtime classes remain module-local.",
                "categories": {
                    name: {"range": f"{lo}-{hi}", "description": description}
                    for name, (lo, hi, description) in self.categories_for(prefix).items()
                },
                "codes": {
                    str(c.code_num): {
                        "name": c.class_name,
                        "owner": c.owner_id,
                        "module": c.module,
                        "category": c.band,
                        "description": c.description,
                        "source": c.source_path,
                        "base_class": c.base_class,
                        "to_inbox": c.to_inbox,
                        "introduced": c.created_at,
                        "updated_at": c.updated_at,
                    }
                    for c in self.list_claims(prefix)
                },
            }
        return {
            "version": self.version,
            "updated_at": _utc(),
            "note": (
                "Per-prefix unique code numbers. Classes may live in different files/projects; "
                "this ledger prevents FINJA-820 meaning two different things."
            ),
            "prefixes": {
                p: {k: c.to_dict() for k, c in sorted(claims.items(), key=lambda x: int(x[0]))}
                for p, claims in sorted(self.prefixes.items())
            },
        }

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        self.path = path
        return path


def load_ledger(path: Optional[Path] = None) -> CodeLedger:
    path = path or default_ledger_path()
    led = CodeLedger(path=path)
    if not path.is_file():
        return led
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return led
    if isinstance(data.get("namespaces"), dict):
        led.public_legend_schema = True
        led.version = int(data.get("schema_version") or 1)
        for prefix, namespace in data["namespaces"].items():
            prefix = str(prefix).upper()
            led.prefixes[prefix] = {}
            parsed_categories: dict[str, tuple[int, int, str]] = {}
            for name, raw_category in (namespace.get("categories") or {}).items():
                if not isinstance(raw_category, dict) or "range" not in raw_category:
                    continue
                lo, hi = str(raw_category["range"]).split("-", 1)
                parsed_categories[str(name)] = (
                    int(lo),
                    int(hi),
                    str(raw_category.get("description") or name),
                )
            led.categories[prefix] = parsed_categories or dict(DEFAULT_BANDS)
            for key, raw in (namespace.get("codes") or {}).items():
                if not isinstance(raw, dict):
                    continue
                claim = CodeClaim.from_dict(
                    {
                        "code_num": int(key),
                        "class_name": raw.get("name"),
                        "band": raw.get("category"),
                        "prefix": prefix,
                        "owner_id": raw.get("owner"),
                        "module": raw.get("module"),
                        "description": raw.get("description"),
                        "source_path": raw.get("source"),
                        "base_class": raw.get("base_class"),
                        "to_inbox": raw.get("to_inbox", True),
                        "created_at": raw.get("introduced"),
                        "updated_at": raw.get("updated_at"),
                    },
                    prefix=prefix,
                )
                led.prefixes[prefix][str(claim.code_num)] = claim
        return led
    if data.get("namespace") and isinstance(data.get("codes"), dict):
        prefix = str(data["namespace"]).upper()
        led.namespace_schema = True
        led.namespace = prefix
        led.version = int(data.get("schema_version") or 1)
        led.prefixes[prefix] = {}
        parsed_categories: dict[str, tuple[int, int, str]] = {}
        for name, raw_category in (data.get("categories") or {}).items():
            if not isinstance(raw_category, dict) or "range" not in raw_category:
                continue
            lo, hi = str(raw_category["range"]).split("-", 1)
            parsed_categories[str(name)] = (
                int(lo),
                int(hi),
                str(raw_category.get("description") or name),
            )
        led.categories[prefix] = parsed_categories or dict(DEFAULT_BANDS)
        for key, raw in data["codes"].items():
            if not isinstance(raw, dict):
                continue
            normalized = {
                "code_num": int(key),
                "class_name": raw.get("name"),
                "band": raw.get("category"),
                "prefix": prefix,
                "owner_id": raw.get("owner"),
                "module": raw.get("module"),
                "description": raw.get("description"),
                "source_path": raw.get("source"),
                "base_class": raw.get("base_class"),
                "to_inbox": raw.get("to_inbox", True),
                "created_at": raw.get("introduced"),
                "updated_at": raw.get("updated_at"),
            }
            claim = CodeClaim.from_dict(normalized, prefix=prefix)
            led.prefixes[prefix][str(claim.code_num)] = claim
        return led
    led.version = int(data.get("version") or 1)
    for pref, claims in (data.get("prefixes") or {}).items():
        led.prefixes[pref.upper()] = {}
        if not isinstance(claims, dict):
            continue
        for k, raw in claims.items():
            if not isinstance(raw, dict):
                continue
            c = CodeClaim.from_dict(raw, prefix=pref)
            led.prefixes[pref.upper()][str(c.code_num)] = c
    return led


def import_taxonomy_into_ledger(
    led: CodeLedger,
    *,
    prefix: str,
    owner_id: str,
    tax_codes: list[Any],
    source_path: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Bootstrap ledger from a Taxonomy / exceptions parse (owner claims all)."""
    prefix = prefix.upper()
    added, skipped, conflicts = 0, 0, []
    for c in tax_codes:
        if isinstance(c, dict):
            num = int(c.get("code_num") or 0)
            class_name = str(c.get("class_name") or f"Error{num}")
            band = str(c.get("band") or band_for_num(num))
            base = str(c.get("base_class") or "AppError")
            inbox = bool(c.get("to_inbox", True))
            desc = str(c.get("message_hint") or "")
            src = str(source_path or c.get("source_file") or "")
        else:
            num = int(getattr(c, "code_num", 0) or 0)
            class_name = str(getattr(c, "class_name", None) or f"Error{num}")
            band = str(getattr(c, "band", None) or band_for_num(num))
            base = str(getattr(c, "base_class", None) or "AppError")
            inbox = bool(getattr(c, "to_inbox", True))
            desc = str(getattr(c, "message_hint", "") or "")
            src = str(source_path or getattr(c, "source_file", "") or "")
        if not num:
            continue
        claim = CodeClaim(
            code_num=num,
            class_name=class_name,
            band=band or band_for_num(num),
            prefix=prefix,
            owner_id=owner_id,
            module="",
            description=desc,
            source_path=src or source_path,
            base_class=base,
            to_inbox=inbox,
        )
        try:
            existing = led.get(prefix, num)
            if existing and existing.owner_id == owner_id and existing.class_name == claim.class_name:
                skipped += 1
                continue
            # Core import wins over accidental wrong reserves for same owner space
            led.upsert(claim, force=force or (existing is not None and existing.owner_id != owner_id and owner_id == "finja"))
            added += 1
        except ValueError as e:
            conflicts.append(str(e))
    return {"added": added, "skipped": skipped, "conflicts": conflicts, "prefix": prefix, "owner_id": owner_id}


def reserve_code(
    led: CodeLedger,
    *,
    prefix: str,
    band: str,
    owner_id: str,
    module: str = "",
    description: str = "",
    class_name: str = "",
    base_class: str = "AppError",
    source_path: str = "",
    to_inbox: bool = True,
    code_num: Optional[int] = None,
    extra_used: Optional[set[int]] = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Reserve next free (or explicit) number in prefix space. Does not require writing a class file."""
    prefix = prefix.upper()
    aliases = {
        "auth": "session",
        "guard": "pipeline",
        "safety": "pipeline",
        "system": "host",
        "generic": "unexpected",
        "tools": "tool",
        "plugins": "tool",
        "obs": "tool",
        "twitch": "session",
        "chat": "session",
    }
    normalized_band = aliases.get(band.lower().strip().replace("-", "_"), band.lower().strip().replace("-", "_"))
    category = led.categories_for(prefix).get(normalized_band)
    if category is None:
        return {
            "ok": False,
            "error": (
                f"Unknown category '{normalized_band}' for {prefix}. "
                "Add it first with `error-contract category`."
            ),
        }
    if code_num is not None:
        num = int(code_num)
        if not category[0] <= num <= category[1]:
            return {
                "ok": False,
                "error": (
                    f"{prefix}-{num} is outside category '{normalized_band}' "
                    f"({category[0]}-{category[1]})"
                ),
            }
        existing = led.get(prefix, num)
        if existing and existing.owner_id not in ("", owner_id):
            return {
                "ok": False,
                "error": f"{prefix}-{num} owned by {existing.owner_id} ({existing.class_name})",
                "existing": existing.to_dict(),
            }
    else:
        # also exclude nums from extra (e.g. local file not yet in ledger)
        num = led.next_free(prefix, band, extra_used=extra_used)
        if num is None:
            return {"ok": False, "error": f"No free slot in band '{band}' for prefix {prefix}"}

    name = class_name or suggest_class_name(band, description)
    # unique class name within prefix ledger
    names = {c.class_name for c in led.claims_for(prefix).values()}
    if name in names and (not led.get(prefix, num) or led.get(prefix, num).class_name != name):
        name = f"{name.removesuffix('Error')}{num}Error"

    b = normalized_band
    claim = CodeClaim(
        code_num=num,
        class_name=name,
        band=b if b in led.categories_for(prefix) else band_for_num(num),
        prefix=prefix,
        owner_id=owner_id,
        module=module,
        description=description,
        source_path=source_path,
        base_class=base_class,
        to_inbox=to_inbox,
    )
    try:
        led.upsert(claim, force=False)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if persist:
        led.save()

    skeleton = _skeleton(claim)
    return {
        "ok": True,
        "code": claim.branded(),
        "claim": claim.to_dict(),
        "skeleton": skeleton,
        "note": (
            "Reserved in the namespace registry. Class may live in a module-local file "
            "(not necessarily the namespace core). Other owners under this prefix "
            "must not reuse this number."
        ),
    }


def _skeleton(claim: CodeClaim) -> str:
    mod = claim.module or claim.band
    msg = claim.description or claim.class_name
    return (
        f"class {claim.class_name}({claim.base_class}):\n"
        f"    code_num = {claim.code_num}\n"
        f"    def __init__(self, message: str = {msg!r}, **kw):\n"
        f"        super().__init__(message, module=kw.pop('module', {mod!r}), **kw)\n"
    )


def apply_class_to_file(
    path: str | Path,
    claim: CodeClaim,
    *,
    base_import_hint: str = "",
) -> dict[str, Any]:
    """Append class skeleton to an exceptions-like file if not already present.

    Does NOT dump into Finja core unless path points there - caller chooses target.
    """
    path = Path(path)
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            '"""Module-local structured errors. Numbers are reserved in the namespace registry."""\n'
            "from __future__ import annotations\n\n"
            f"# Shared base import when available: {base_import_hint or 'from core.exceptions import AppError'}\n\n"
            "class AppError(Exception):\n"
            "    code_num = None\n"
            "    def __init__(self, message: str = '', module: str = 'unknown', **kw):\n"
            "        self.module = module\n"
            "        super().__init__(message)\n\n"
        )

    if re.search(rf"code_num\s*=\s*{claim.code_num}\b", text):
        return {
            "ok": True,
            "action": "already_present",
            "path": str(path),
            "note": f"code_num={claim.code_num} already in file - not duplicated",
        }
    if re.search(rf"class\s+{re.escape(claim.class_name)}\b", text):
        return {
            "ok": True,
            "action": "class_name_exists",
            "path": str(path),
            "note": f"class {claim.class_name} already exists",
        }

    block = (
        f"\n# --- {claim.branded()} [{claim.band}] owner={claim.owner_id} module={claim.module} ---\n"
        f"# Ledger-reserved: do not reuse this number under prefix {claim.prefix}\n"
        f"{_skeleton(claim)}"
    )
    path.write_text(text.rstrip() + "\n" + block + "\n", encoding="utf-8")
    return {"ok": True, "action": "appended", "path": str(path)}


def check_local_against_ledger(
    led: CodeLedger,
    *,
    prefix: str,
    local_codes: list[Any],
    owner_id: str = "",
) -> list[dict[str, Any]]:
    """Find collisions: local file uses a number owned by someone else."""
    issues: list[dict[str, Any]] = []
    prefix = prefix.upper()
    for c in local_codes:
        num = int(getattr(c, "code_num", 0) or 0)
        if not num:
            continue
        name = getattr(c, "class_name", "")
        claim = led.get(prefix, num)
        if not claim:
            issues.append(
                {
                    "severity": "info",
                    "code": f"{prefix}-{num}",
                    "issue": "local_unregistered",
                    "message": f"{name} uses {prefix}-{num} but ledger has no claim - run ledger-import",
                }
            )
            continue
        if claim.owner_id and owner_id and claim.owner_id != owner_id:
            issues.append(
                {
                    "severity": "critical",
                    "code": f"{prefix}-{num}",
                    "issue": "number_collision",
                    "message": (
                        f"Local {name} claims {prefix}-{num}, but the registry assigns it to "
                        f"{claim.class_name} (owner={claim.owner_id})."
                    ),
                    "ledger": claim.to_dict(),
                }
            )
        elif claim.class_name != name and claim.owner_id == owner_id:
            issues.append(
                {
                    "severity": "medium",
                    "code": f"{prefix}-{num}",
                    "issue": "class_rename",
                    "message": f"Ledger has {claim.class_name}, local has {name} for same number",
                }
            )
    return issues


def format_ledger(led: CodeLedger, prefix: str = "", limit: int = 0) -> str:
    claims = led.list_claims(prefix)
    if limit:
        claims = claims[:limit]
    lines = [
        f"Code ledger: {led.path}",
        f"Prefixes: {', '.join(sorted(led.prefixes.keys())) or '(empty)'}",
        f"Showing: {len(claims)} claims" + (f" (prefix={prefix})" if prefix else ""),
        "",
        f"{'Code':<14} {'Owner':<16} {'Module':<16} {'Class':<28} Band",
        "-" * 90,
    ]
    for c in claims:
        lines.append(
            f"{c.branded():<14} {(c.owner_id or '-'):<16} {(c.module or '-'):<16} "
            f"{c.class_name:<28} {c.band}"
        )
    if not claims:
        lines.append("(no claims - run: error-contract ledger-import --finja-core ...)")
    lines.append("")
    lines.append(
        "Rule: same PREFIX â‡’ unique numbers worldwide. Different PREFIX (AST vs FINJA) = separate space."
    )
    lines.append("Rule: class file location â‰  number ownership. OBS can live outside Finja core.")
    return "\n".join(lines) + "\n"


def bootstrap_finja_core(led: CodeLedger, exceptions_path: str | Path, owner_id: str = "finja") -> dict[str, Any]:
    path = Path(exceptions_path)
    if path.is_file():
        tax = parse_exceptions_py(path, prefix_hint="FINJA")
        tax.prefix = "FINJA"
        result = import_taxonomy_into_ledger(
            led,
            prefix="FINJA",
            owner_id=owner_id,
            tax_codes=tax.codes,
            source_path=str(path),
        )
    else:
        tax = finja_reference_taxonomy()
        result = import_taxonomy_into_ledger(
            led,
            prefix="FINJA",
            owner_id=owner_id,
            tax_codes=tax.codes,
            source_path="builtin:finja",
        )
        result["note"] = "exceptions path missing - imported builtin reference"
    led.save()
    result["ledger"] = str(led.path)
    result["total_finja"] = len(led.claims_for("FINJA"))
    return result
