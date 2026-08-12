"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / headers
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Cross-project J. Apps file-header templates and detection.

  New in v1.1.0:
    - Separated plugin identity from generated target-project identity

  New in v1.0.1:
    - README footer accepts the correct repository-relative LICENSE path

  New in v1.0.0:
    - Python / Batch / HTML / JS header builders matching ecosystem style
    - Version field MUST match module version (MAJOR.FEATURES.BUGS)

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

VERSION_RE = re.compile(
    r"(?im)^\s*(?:#|//|@REM|<!--)?\s*Version:\s*v?(\d+\.\d+\.\d+)"
)
# also Version: 1.0.0 inside banners
VERSION_INLINE_RE = re.compile(r"(?i)Version:\s*v?(\d+\.\d+\.\d+)")
HEADER_MARKERS = (
    "Project:",
    "Author:",
    "Version:",
    "Copyright (c)",
    "Licensed under the MIT",
    "J. Apps",
)

DEFAULT_PROJECT = "J. Apps Project"
DEFAULT_AUTHOR = "J. Apps (JohnV2002 / Sodakiller1)"
DEFAULT_WEBSITE = "https://jappshome.de"
DEFAULT_SUPPORT = "https://buymeacoffee.com/J.Apps"
DEFAULT_EMAIL = "contact@jappshome.de"


def extract_version(text: str) -> Optional[str]:
    m = VERSION_INLINE_RE.search(text[:4000])
    return m.group(1) if m else None


def has_ecosystem_header(text: str, path: Path | None = None) -> bool:
    head = text[:2500]
    hits = sum(1 for m in HEADER_MARKERS if m in head)
    if hits >= 3:
        return True
    # HTML comment banner
    if path and path.suffix.lower() in {".html", ".htm"}:
        return "Project:" in head and "Version:" in head
    # batch
    if path and path.suffix.lower() in {".bat", ".cmd"}:
        return "@REM" in head[:500] and "Version:" in head
    return False


def build_python_header(
    *,
    title: str,
    module: str,
    version: str,
    description: str,
    new_in: list[str] | None = None,
    project: str = DEFAULT_PROJECT,
) -> str:
    new_lines = ""
    if new_in:
        new_lines = "\n  New in v{ver}:\n".format(ver=version)
        for item in new_in:
            new_lines += f"    - {item}\n"
    desc = description.strip() or title
    return f'''"""
======================================================================
         {title}
======================================================================

  Project: {project}
  Module:  {module}
  Author:  {DEFAULT_AUTHOR}
  Version: {version}
  Description: {desc}
{new_lines}
----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with love by Sodakiller1 (J. Apps / JohnV2002)
  Website: {DEFAULT_WEBSITE}
  Support: {DEFAULT_SUPPORT}

======================================================================
"""
'''


def build_batch_header(
    *,
    title: str,
    version: str,
    description: str,
    new_in: list[str] | None = None,
    project: str = DEFAULT_PROJECT,
) -> str:
    lines = [
        "@REM ======================================================================",
        f"@REM                  {title}",
        "@REM ======================================================================",
        "@REM",
        f"@REM   Project: {project}",
        f"@REM   Author: {DEFAULT_AUTHOR}",
        f"@REM   Version: {version}",
        f"@REM   Description: {description}",
        "@REM",
    ]
    if new_in:
        lines.append(f"@REM   New in {version}:")
        for item in new_in:
            lines.append(f"@REM     - {item}")
        lines.append("@REM")
    lines += [
        "@REM   Copyright (c) 2026 J. Apps",
        "@REM   Licensed under the MIT License.",
        "@REM",
        "@REM ======================================================================",
        "",
    ]
    return "\n".join(lines)


def build_html_header(
    *,
    title: str,
    version: str,
    description: str,
    new_in: list[str] | None = None,
    project: str = DEFAULT_PROJECT,
) -> str:
    lines = [
        "<!-- ====================================================================== -->",
        f"<!--                      {title}                      -->",
        "<!-- ====================================================================== -->",
        "<!--                                                                        -->",
        f"<!--   Project: {project}                          -->",
        f"<!--   Author: {DEFAULT_AUTHOR}                            -->",
        f"<!--   Version: {version}                                                       -->",
        f"<!--   Description: {description} -->",
        "<!--                                                                        -->",
    ]
    if new_in:
        lines.append(f"<!--   New in {version}:                                                     -->")
        for item in new_in:
            lines.append(f"<!--     - {item} -->")
        lines.append("<!--                                                                        -->")
    lines += [
        "<!--   Copyright (c) 2026 J. Apps                                           -->",
        "<!--   Licensed under the MIT License.                                      -->",
        "<!-- ====================================================================== -->",
        "",
    ]
    return "\n".join(lines)


def build_readme_footer(license_path: str = "../LICENSE") -> str:
    return f"""
## License

**MIT** (c) J. Apps — full text: repository root [`LICENSE`]({license_path}).

## Support & Contact

- **Email:** {DEFAULT_EMAIL}
- **Website:** [{DEFAULT_WEBSITE.replace('https://', '')}]({DEFAULT_WEBSITE})
- **Support:** [Buy Me a Coffee]({DEFAULT_SUPPORT})
"""
