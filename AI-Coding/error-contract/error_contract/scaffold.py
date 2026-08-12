"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/scaffold.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Scaffold a minimal module-local exception implementation and manifest.

  New in v1.3.1:
    - Uses one public repo-root legend instead of copying all codes

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

from pathlib import Path

from .manifest import build_local_manifest, write_local_manifest
from .ledger import canonical_registry_path, load_namespace_ledger


def scaffold_project(
    root: str | Path,
    *,
    prefix: str,
    name: str = "",
    package_dir: str = "core",
    force: bool = False,
    slim: bool = True,
    owner: str = "",
    module: str = "",
) -> dict[str, str]:
    """Create a minimal local implementation; reserve no namespace codes."""
    del slim  # kept for CLI compatibility with 1.0
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    prefix = prefix.strip().upper() or "APP"
    project_name = name or root.name
    owner = owner or project_name.lower().replace(" ", "-")
    module = module or owner

    core = root / package_dir
    core.mkdir(parents=True, exist_ok=True)
    exc_path = core / "exceptions.py"
    contract_path = root / "contracts" / "error_contract.module.json"
    legend_path = canonical_registry_path(prefix, root)
    written: dict[str, str] = {}

    if not exc_path.exists() or force:
        exc_path.write_text(_render_exceptions(prefix=prefix, project_name=project_name), encoding="utf-8")
        written["exceptions.py"] = str(exc_path)
    else:
        written["exceptions.py"] = f"SKIP exists: {exc_path}"

    if not contract_path.exists() or force:
        manifest = build_local_manifest(
            root=root,
            prefix=prefix,
            owner=owner,
            module=module,
            exceptions_path=exc_path,
            local_codes=[],
            legend_path=legend_path,
        )
        write_local_manifest(contract_path, manifest)
        written["error_contract.json"] = str(contract_path)
    else:
        written["error_contract.json"] = f"SKIP exists: {contract_path}"

    legend = load_namespace_ledger(prefix, root)
    if prefix not in legend.prefixes:
        legend.prefixes.setdefault(prefix, {})
        legend.save()
        written["root_error_contract.json"] = str(legend_path)

    init = core / "__init__.py"
    if not init.exists():
        init.write_text('"""Project core package."""\n', encoding="utf-8")
        written["__init__.py"] = str(init)
    return written


def _render_exceptions(*, prefix: str, project_name: str) -> str:
    return f'''"""Structured errors used locally by {project_name}.

Numeric codes are reserved in the repository-root error_contract.json legend.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "{prefix}"


def set_code_prefix(prefix: str) -> None:
    global CODE_PREFIX
    CODE_PREFIX = (prefix or "APP").strip().upper()


class AppError(Exception):
    """Non-numbered base; concrete module errors own the numeric codes."""

    code_num: Optional[int] = None
    to_inbox: bool = True

    def __init__(self, message: str, module: str = "unknown", cause: Optional[Exception] = None, **context: Any) -> None:
        self.module = module
        self.context = context
        self.cause = cause
        super().__init__(message)

    @property
    def code(self) -> str:
        if self.code_num is None:
            raise TypeError("AppError base classes do not own an error code")
        return f"{{CODE_PREFIX}}-{{self.code_num}}"

    def for_dashboard(self) -> dict[str, Any]:
        target = self.cause if self.cause is not None else self
        trace = ""
        if getattr(target, "__traceback__", None) is not None:
            trace = "".join(traceback.format_exception(type(target), target, target.__traceback__, limit=4))
        return {{
            "code": self.code,
            "message": str(self),
            "module": self.module,
            "context": self.context,
            "cause": f"{{type(self.cause).__name__}}: {{self.cause}}" if self.cause else None,
            "traceback": trace,
            "to_inbox": self.to_inbox,
        }}


# Add concrete module errors only through `error-contract create`.
'''
