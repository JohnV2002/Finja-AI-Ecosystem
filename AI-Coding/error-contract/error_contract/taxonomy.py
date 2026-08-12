"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/taxonomy.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Parse Finja-style exceptions.py, propose free codes, Finja reference taxonomy.

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

import ast
import json
import re
from pathlib import Path
from typing import Any, Optional

from .models import DEFAULT_BANDS, ErrorCode, Taxonomy

# class FooError(BarError):
_CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*([\w\.]+)\s*\)\s*:",
    re.MULTILINE,
)
_CODE_NUM_RE = re.compile(r"code_num\s*=\s*(\d+)")
_TO_INBOX_RE = re.compile(r"to_inbox\s*=\s*(True|False)")
_PREFIX_ASSIGN_RE = re.compile(
    r"""CODE_PREFIX\s*=\s*['"]([A-Za-z][A-Za-z0-9_]*)['"]"""
)
_SET_PREFIX_RE = re.compile(
    r"""set_code_prefix\s*\(\s*['"]([A-Za-z][A-Za-z0-9_]*)['"]"""
)
_BAND_COMMENT_RE = re.compile(
    r"#\s*---\s*(\d+)xx\s+([A-Z][A-Z0-9 /_|-]+)",
    re.IGNORECASE,
)
_BRANDED_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,12})-(\d{2,4})\b")


def band_for_num(num: int, bands: dict[str, tuple[int, int, str]] | None = None) -> str:
    bands = bands or DEFAULT_BANDS
    for name, (lo, hi, _) in bands.items():
        if lo <= num <= hi:
            return name
    return "other"


def parse_exceptions_py(path: str | Path, prefix_hint: str = "") -> Taxonomy:
    """Extract ErrorCode entries from a Finja-style exceptions.py."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    tax = Taxonomy(
        prefix=(prefix_hint or "APP").upper(),
        source=str(path),
        style="finja_app_error",
        bands=dict(DEFAULT_BANDS),
    )

    if "class AppError" in text or "class AppError(" in text:
        tax.has_app_error = True
    if "set_code_prefix" in text:
        tax.has_set_code_prefix = True

    m = _PREFIX_ASSIGN_RE.search(text)
    if m and not prefix_hint:
        tax.prefix = m.group(1).upper()

    # Prefer AST for class bodies (code_num on class)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _parse_exceptions_regex(text, tax)

    # First pass: collect class metadata (order matters for inheritance)
    raw: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)
        base = bases[0] if bases else "Exception"
        code_num: Optional[int] = None
        to_inbox: Optional[bool] = None
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id == "code_num" and isinstance(stmt.value, ast.Constant):
                    if isinstance(stmt.value.value, int):
                        code_num = stmt.value.value
                if isinstance(t, ast.Name) and t.id == "to_inbox" and isinstance(stmt.value, ast.Constant):
                    if isinstance(stmt.value.value, bool):
                        to_inbox = stmt.value.value
        if code_num is None:
            continue
        doc = ast.get_docstring(node) or ""
        meta = {
            "code_num": code_num,
            "class_name": node.name,
            "base_class": base,
            "to_inbox": to_inbox,
            "doc": doc,
            "lineno": node.lineno,
        }
        raw.append(meta)
        by_name[node.name] = meta

    def resolve_inbox(name: str, seen: set[str] | None = None) -> bool:
        """Inherit to_inbox along the base chain (PrivacyLeakError <- PrivacyError)."""
        seen = seen or set()
        if name in seen:
            return True
        seen.add(name)
        meta = by_name.get(name)
        if not meta:
            return True
        if meta["to_inbox"] is not None:
            return bool(meta["to_inbox"])
        return resolve_inbox(meta["base_class"], seen)

    for meta in raw:
        code_num = int(meta["code_num"])
        doc = meta["doc"] or ""
        tax.codes.append(
            ErrorCode(
                code_num=code_num,
                class_name=meta["class_name"],
                base_class=meta["base_class"],
                band=band_for_num(code_num),
                message_hint=doc.strip().splitlines()[0] if doc else "",
                to_inbox=resolve_inbox(meta["class_name"]),
                source_file=str(path),
                source_line=int(meta["lineno"]),
            )
        )

    # Fill gaps if AST missed nested / unusual assignments
    if not tax.codes:
        return _parse_exceptions_regex(text, tax)

    return tax


def _parse_exceptions_regex(text: str, tax: Taxonomy) -> Taxonomy:
    """Fallback when AST fails: walk class blocks with regex."""
    matches = list(_CLASS_RE.finditer(text))
    for i, m in enumerate(matches):
        name, base = m.group(1), m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        cm = _CODE_NUM_RE.search(block)
        if not cm:
            continue
        code_num = int(cm.group(1))
        im = _TO_INBOX_RE.search(block)
        to_inbox = True if not im else im.group(1) == "True"
        tax.codes.append(
            ErrorCode(
                code_num=code_num,
                class_name=name,
                base_class=base,
                band=band_for_num(code_num),
                to_inbox=to_inbox,
                source_file=tax.source,
            )
        )
    return tax


def parse_contract_json(path: str | Path, prefix_hint: str = "") -> Taxonomy:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data.get("namespaces"), dict):
        namespaces = data["namespaces"]
        selected = prefix_hint.upper() if prefix_hint and prefix_hint.upper() in namespaces else ""
        if not selected and len(namespaces) == 1:
            selected = next(iter(namespaces)).upper()
        namespace = namespaces.get(selected) or {}
        data = {
            "prefix": selected or "APP",
            "bands": namespace.get("categories") or {},
            "codes": [
                {"code_num": int(number), **claim}
                for number, claim in (namespace.get("codes") or {}).items()
            ],
        }
    elif isinstance(data.get("implementations"), list):
        data = {
            "prefix": data.get("namespace") or prefix_hint or "APP",
            "codes": [
                {
                    "code": item.get("code"),
                    "name": item.get("name"),
                    "source": item.get("source"),
                }
                for item in data["implementations"]
            ],
        }
    tax = Taxonomy(
        prefix=str(data.get("prefix") or "APP").upper(),
        source=str(path),
        style="json_contract",
        has_app_error=bool(data.get("has_app_error", True)),
        has_set_code_prefix=bool(data.get("has_set_code_prefix", True)),
    )
    if "bands" in data and isinstance(data["bands"], dict):
        bands: dict[str, tuple[int, int, str]] = {}
        for k, v in data["bands"].items():
            if isinstance(v, dict):
                if "range" in v:
                    lo, hi = str(v["range"]).split("-", 1)
                    bands[k] = (int(lo), int(hi), str(v.get("description") or k))
                else:
                    bands[k] = (int(v["lo"]), int(v["hi"]), str(v.get("label") or k))
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                bands[k] = (int(v[0]), int(v[1]), str(v[2] if len(v) > 2 else k))
        if bands:
            tax.bands = bands
    for c in data.get("codes") or []:
        num = int(c.get("code_num") or c.get("num") or 0)
        if not num:
            # allow "FINJA-502"
            code = str(c.get("code") or "")
            bm = _BRANDED_CODE_RE.fullmatch(code) or _BRANDED_CODE_RE.search(code)
            if bm:
                if not data.get("prefix"):
                    tax.prefix = bm.group(1).upper()
                num = int(bm.group(2))
        if not num:
            continue
        tax.codes.append(
            ErrorCode(
                code_num=num,
                class_name=str(c.get("class_name") or c.get("name") or f"Error{num}"),
                base_class=str(c.get("base_class") or "AppError"),
                band=str(c.get("band") or c.get("category") or band_for_num(num, tax.bands)),
                message_hint=str(c.get("message_hint") or c.get("description") or ""),
                to_inbox=bool(c.get("to_inbox", True)),
                module_default=str(c.get("module_default") or ""),
                source_file=str(path),
            )
        )
    return tax


def dump_contract_json(tax: Taxonomy, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(tax.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge_prefix_from_config(tax: Taxonomy, project_root: str | Path) -> Taxonomy:
    """Try runtime_config.json / .env-ish code_prefix."""
    root = Path(project_root)
    candidates = [
        root / "config" / "runtime_config.json",
        root / "runtime_config.json",
        root / "error_contract.json",
        root / "contracts" / "error_contract.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        prefix = data.get("code_prefix") or data.get("prefix")
        if prefix:
            tax.prefix = str(prefix).strip().upper()
            break
    return tax


def suggest_class_name(band: str, message: str = "") -> str:
    """Rough class name suggestion for a new code."""
    words = re.findall(r"[A-Za-z]+", message)
    if words:
        base = "".join(w.capitalize() for w in words[:4])
        if not base.endswith("Error"):
            base += "Error"
        return base
    band_map = {
        "config": "ConfigError",
        "llm": "LLMError",
        "memory": "MemoryStoreError",
        "session": "SessionError",
        "tool": "ToolError",
        "pipeline": "PipelineError",
        "host": "HostError",
        "unexpected": "UnexpectedError",
        "privacy": "PrivacyError",
        "injection": "PromptInjectionError",
    }
    return band_map.get(band, "AppError")


def propose_code(
    tax: Taxonomy,
    *,
    project_root: str | Path = ".",
    band: str,
    message: str = "",
    class_name: str = "",
    use_global_ledger: bool = True,
    owner_id: str = "",
    module: str = "",
    reserve: bool = False,
) -> dict[str, Any]:
    """Propose a new branded code in a free slot of the given band.

    When use_global_ledger=True (default), free slots also exclude numbers
    claimed by *other* projects under the same prefix (prevents FINJA-820
    meaning two different things). Does not write a class file unless reserve=True
    (then only ledger reservation, still no core dump).
    """
    band = band.lower().strip().replace("-", "_")
    ledger_info = None
    led = None
    if use_global_ledger:
        try:
            from .ledger import load_namespace_ledger

            led = load_namespace_ledger(tax.prefix, project_root)
            tax.bands.update(led.categories_for(tax.prefix))
            ledger_info = str(led.path)
        except Exception:
            pass
    if band not in tax.bands:
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

    extra_used: set[int] = set(tax.used_nums())
    if led is not None:
        try:
            extra_used |= led.used_nums(tax.prefix)
        except Exception:
            pass

    # next free considering ledger + local tax
    info = tax.bands.get(band)
    if not info:
        return {"ok": False, "error": f"Unknown band '{band}'", "band": band}
    lo, hi, label = info
    num = None
    for n in range(lo, hi + 1):
        if n not in extra_used:
            num = n
            break
    if num is None:
        return {
            "ok": False,
            "error": f"No free slot in band '{band}' (local + repository legend)",
            "band": band,
            "used": sorted(n for n in extra_used if lo <= n <= hi),
            "ledger": ledger_info,
        }

    name = class_name or suggest_class_name(band, message)
    existing_names = {c.class_name for c in tax.codes}
    if name in existing_names:
        name = f"{name.removesuffix('Error')}{num}Error"

    result: dict[str, Any] = {
        "ok": True,
        "code": f"{tax.prefix}-{num}",
        "code_num": num,
        "class_name": name,
        "band": band,
        "band_label": label,
        "message_hint": message,
        "ledger": ledger_info,
        "reserved": False,
        "skeleton": (
            f"class {name}(AppError):\n"
            f"    code_num = {num}\n"
            f"    def __init__(self, message: str = {message!r}, **kw):\n"
            f"        super().__init__(message, module=kw.pop('module', {(module or band)!r}), **kw)\n"
        ),
        "placement_note": (
            "Number is unique under this PREFIX (repository legend). "
            "Put the class in the owning module's error file - "
            "NOT necessarily Finja core/exceptions.py (OBS/chat can stay local)."
        ),
    }

    if reserve and owner_id:
        from .ledger import load_namespace_ledger, reserve_code

        led = load_namespace_ledger(tax.prefix, project_root)
        r = reserve_code(
            led,
            prefix=tax.prefix,
            band=band,
            owner_id=owner_id,
            module=module,
            description=message,
            class_name=name,
            extra_used=tax.used_nums(),
            persist=True,
        )
        if not r.get("ok"):
            return r
        result["reserved"] = True
        result["claim"] = r.get("claim")
        result["code"] = r.get("code")
        result["skeleton"] = r.get("skeleton") or result["skeleton"]
    return result


def finja_reference_taxonomy() -> Taxonomy:
    """Built-in Finja reference (mirrors core/exceptions.py)."""
    codes = [
        ("AppError", "Exception", 900, True),
        ("ConfigError", "AppError", 100, True),
        ("EnvError", "ConfigError", 101, True),
        ("MissingPackageError", "ConfigError", 102, True),
        ("LLMError", "AppError", 200, True),
        ("LLMTimeoutError", "LLMError", 201, True),
        ("LLMConnectionError", "LLMError", 202, True),
        ("EmptyResponseError", "LLMError", 204, True),
        ("RateLimitError", "LLMError", 205, True),
        ("ModelNotFoundError", "LLMError", 206, True),
        ("AllProvidersFailedError", "LLMError", 210, True),
        ("MemoryStoreError", "AppError", 300, True),
        ("MemoryServerError", "MemoryStoreError", 303, True),
        ("DiaryCorruptError", "MemoryStoreError", 340, True),
        ("MemoryStoreCorruptError", "MemoryStoreError", 341, True),
        ("SessionError", "AppError", 400, True),
        ("AuthError", "SessionError", 401, True),
        ("UserNotFoundError", "SessionError", 402, True),
        ("NoPrivilegeError", "SessionError", 444, True),
        ("ToolError", "AppError", 500, True),
        ("ToolNotFoundError", "ToolError", 501, True),
        ("ToolExecutionError", "ToolError", 502, True),
        ("ToolTimeoutError", "ToolError", 503, True),
        ("PipelineError", "AppError", 600, True),
        ("GuardError", "PipelineError", 601, True),
        ("SafetyError", "PipelineError", 602, True),
        ("UserInputError", "PipelineError", 610, True),
        ("HostError", "AppError", 800, True),
        ("MaintenanceError", "HostError", 803, True),
        ("UnexpectedError", "AppError", 999, True),
        ("PrivacyError", "AppError", 1000, False),
        ("PrivacyLeakError", "PrivacyError", 1001, False),
        ("PromptInjectionError", "AppError", 1100, False),
    ]
    tax = Taxonomy(prefix="FINJA", source="builtin:finja", style="finja_app_error", has_app_error=True, has_set_code_prefix=True)
    for name, base, num, inbox in codes:
        tax.codes.append(
            ErrorCode(
                code_num=num,
                class_name=name,
                base_class=base,
                band=band_for_num(num),
                to_inbox=inbox,
            )
        )
    return tax
