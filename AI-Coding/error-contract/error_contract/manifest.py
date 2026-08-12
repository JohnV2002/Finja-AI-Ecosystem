"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/manifest.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Path-neutral module manifests backed by a public repo-root error legend.

  New in v1.3.1:
    - Separates the public repository legend from module-local implementations

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def relative_source(root: Path, source: Path) -> str:
    """Produce a public-safe logical source path, never an absolute host path."""
    try:
        return source.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return source.name


def legend_reference(module_root: Path, legend_path: Path) -> str:
    """Relative pointer usable by humans without the plugin installed."""
    try:
        return Path(os.path.relpath(legend_path.resolve(), module_root.resolve())).as_posix()
    except ValueError:
        return legend_path.name


def build_local_manifest(
    *,
    root: Path,
    prefix: str,
    owner: str,
    module: str,
    exceptions_path: Path,
    local_codes: list[Any],
    legend_path: Path,
) -> dict[str, Any]:
    source = relative_source(root, exceptions_path)
    implementations = []
    for code in sorted(local_codes, key=lambda item: int(getattr(item, "code_num", 0) or 0)):
        number = int(getattr(code, "code_num", 0) or 0)
        if not number:
            continue
        implementations.append(
            {
                "code": f"{prefix.upper()}-{number}",
                "name": str(getattr(code, "class_name", f"Error{number}")),
                "source": source,
            }
        )
    return {
        "schema_version": 2,
        "namespace": prefix.upper(),
        "owner": owner,
        "module": module or owner,
        "legend": legend_reference(root, legend_path),
        "implementations": implementations,
    }


def write_local_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
