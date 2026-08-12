"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/docsgen.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Maintain the public root legend and module-local machine-readable manifest.

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

from pathlib import Path
from typing import Any, Optional

from .detect import detect_project
from .manifest import build_local_manifest, legend_reference, write_local_manifest
from .ledger import canonical_registry_path, import_taxonomy_into_ledger, load_namespace_ledger
from .registry import Registry, load_registry, resolve_project
from .scaffold import scaffold_project
from .taxonomy import parse_exceptions_py


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def ensure_project_docs(
    path: str | Path,
    *,
    prefix: str = "",
    force: bool = False,
    scaffold_if_missing: bool = False,
    package_dir: str = "core",
    project_name: str = "",
    write_agent_stubs: bool = False,
) -> dict[str, Any]:
    """Maintain the root legend and optional local implementation manifest.

    Never invents a prefix silently when registry says needs_onboard -
    returns status needs_onboard instead (unless prefix forced).
    """
    root = Path(path).expanduser().resolve()
    actions: list[dict[str, str]] = []
    reg = load_registry()
    resolved = resolve_project(root, reg)

    if resolved["status"] == "needs_onboard" and not prefix:
        return {
            "status": "needs_onboard",
            "path": str(root),
            "resolve": resolved,
            "actions": actions,
            "message": "Project not in registry - onboard first (ask human), then ensure again.",
        }

    if resolved["status"] == "known":
        eff_prefix = resolved["effective_prefix"]
        entry = resolved["project"]
        module_default = entry.get("module_default") or ""
    else:
        eff_prefix = prefix.upper()
        entry = None
        module_default = ""

    if prefix:
        eff_prefix = prefix.upper()

    profile = detect_project(root, prefix=eff_prefix)
    # Prefer registry prefix over detect heuristics
    profile.prefix = eff_prefix
    if profile.taxonomy:
        profile.taxonomy.prefix = eff_prefix

    # 1) exceptions scaffold if completely missing and allowed
    if not profile.exceptions_path and not profile.contract_path:
        if scaffold_if_missing:
            written = scaffold_project(
                root,
                prefix=eff_prefix,
                name=project_name or (entry["name"] if entry else root.name),
                package_dir=package_dir,
                force=force,
                owner=(entry.get("id") if entry else ""),
                module=module_default,
            )
            for k, v in written.items():
                actions.append({"action": "scaffold", "file": k, "detail": v})
            profile = detect_project(root, prefix=eff_prefix)
            profile.prefix = eff_prefix
        else:
            actions.append(
                {
                    "action": "missing_exceptions",
                    "file": f"{package_dir}/exceptions.py",
                    "detail": "Run ensure --scaffold or scaffold manually",
                }
            )

    # 2) write a small local implementation manifest, never a namespace copy
    contract_path = root / "contracts" / "error_contract.module.json"
    legend_path = canonical_registry_path(eff_prefix, root)
    if profile.exceptions_path:
        try:
            local_taxonomy = parse_exceptions_py(profile.exceptions_path, prefix_hint=eff_prefix)
            owner = entry.get("id") if entry else root.name.lower()
            ledger = load_namespace_ledger(eff_prefix, root)
            source = legend_reference(legend_path.parent, Path(profile.exceptions_path))
            synced = import_taxonomy_into_ledger(
                ledger,
                prefix=eff_prefix,
                owner_id=owner,
                tax_codes=local_taxonomy.codes,
                source_path=source,
            )
            if synced["conflicts"]:
                actions.append(
                    {
                        "action": "error",
                        "file": legend_reference(root, legend_path),
                        "detail": "; ".join(synced["conflicts"]),
                    }
                )
            else:
                ledger.prefixes.setdefault(eff_prefix, {})
                ledger.save()
                actions.append(
                    {
                        "action": "synced",
                        "file": legend_reference(root, legend_path),
                        "detail": f"public legend; {len(ledger.claims_for(eff_prefix))} {eff_prefix} codes",
                    }
                )
        except OSError as error:
            actions.append({"action": "error", "file": str(legend_path), "detail": str(error)})
    if profile.exceptions_path and (force or not contract_path.is_file()):
        try:
            tax = parse_exceptions_py(profile.exceptions_path, prefix_hint=eff_prefix)
            tax.prefix = eff_prefix
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            manifest = build_local_manifest(
                root=root,
                prefix=eff_prefix,
                owner=(entry.get("id") if entry else root.name.lower()),
                module=module_default,
                exceptions_path=Path(profile.exceptions_path),
                local_codes=tax.codes,
                legend_path=legend_path,
            )
            write_local_manifest(contract_path, manifest)
            actions.append(
                {
                    "action": "wrote" if not force else "rewrote",
                    "file": _rel(root, contract_path),
                    "detail": f"{len(tax.codes)} codes",
                }
            )
        except OSError as e:
            actions.append({"action": "error", "file": str(contract_path), "detail": str(e)})
    elif contract_path.is_file():
        actions.append({"action": "ok", "file": _rel(root, contract_path), "detail": "exists"})

    # 3) Optional lightweight agent stubs (pointer only - skill holds full rules)
    if write_agent_stubs:
        pointer = (
            f"\n## Error Contract\n\n"
            f"This project uses structured errors **{eff_prefix}-xxx**. "
            f"Read the repository-root `error_contract.json` legend. "
            f"Never use print/console.log as the error path. "
            f"Engine: `python -m error_contract` "
            f"(plugin: finja - exception Plugins).\n"
        )
        for stub_name in ("AGENTS.md", "CLAUDE.md"):
            stub = root / stub_name
            if stub.is_file():
                text = stub.read_text(encoding="utf-8-sig", errors="ignore")
                if "Error Contract" in text or "ERROR_CONTRACT.md" in text:
                    actions.append({"action": "ok", "file": stub_name, "detail": "already references contract"})
                    continue
                if force or True:
                    stub.write_text(text.rstrip() + "\n" + pointer, encoding="utf-8")
                    actions.append({"action": "appended", "file": stub_name, "detail": "error contract pointer"})
            else:
                # Only create AGENTS.md by default (less noise); CLAUDE.md only if force
                if stub_name == "AGENTS.md" or force:
                    stub.write_text(
                        f"# {project_name or root.name}\n" + pointer,
                        encoding="utf-8",
                    )
                    actions.append({"action": "wrote", "file": stub_name, "detail": "pointer stub"})
                else:
                    actions.append({"action": "skip", "file": stub_name, "detail": "not created (use --force for CLAUDE.md)"})

    return {
        "status": "ok",
        "path": str(root),
        "prefix": eff_prefix,
        "registry": entry,
        "actions": actions,
        "profile": {
            "exceptions_path": profile.exceptions_path,
            "contract_path": profile.contract_path,
            "detected": profile.detected_systems,
        },
    }


def format_ensure(result: dict[str, Any]) -> str:
    if result.get("status") == "needs_onboard":
        from .registry import format_resolve

        lines = [
            "=== ensure: NEEDS ONBOARD ===",
            result.get("message", ""),
            "",
            format_resolve(result["resolve"]),
        ]
        return "\n".join(lines)

    lines = [
        "=== ensure: docs ===",
        f"Path   : {result.get('path')}",
        f"Prefix : {result.get('prefix')}",
        f"Status : {result.get('status')}",
        "",
        "Actions:",
    ]
    for a in result.get("actions") or []:
        lines.append(f"  [{a.get('action')}] {a.get('file')} - {a.get('detail')}")
    return "\n".join(lines) + "\n"
