"""
Glorpo Native Dictionary Generator
==================================
Regenerates the native C++ deglorpo dictionary from the Python package.

Main Responsibilities:
- Import GLORPO_DICT from the package source.
- Build the reverse Glorpo-to-Python token map.
- Write glorpo_dict.hpp for the native runner.

Side Effects:
- Imports code from glorpo-pkg.
- Writes glorpo_dict.hpp when stdout is not requested.
- Prints generation status to stdout.
"""

import sys
import os

# Locate glorpo.py in the package folder.
script_dir = os.path.dirname(os.path.abspath(__file__))
glorpo_pkg = os.path.join(script_dir, "..", "glorpo-pkg")
sys.path.insert(0, glorpo_pkg)

from glorpo import GLORPO_DICT  # noqa: E402

# Build Glorpo -> Python map, sorted longest-first
deglorpo = {v: k for k, v in GLORPO_DICT.items()}
entries = sorted(deglorpo.items(), key=lambda x: len(x[0]), reverse=True)

lines = [
    "#pragma once",
    "#include <vector>",
    "#include <string>",
    "#include <utility>",
    "",
    f"// Auto-generated from glorpo.py GLORPO_DICT ({len(entries)} tokens).",
    "// Do not edit manually. Regenerate with:",
    "//   python3 gen_dict.py",
    "//",
    "// Glorpo token -> Python token, sorted longest-first (prevents partial matches).",
    "const std::vector<std::pair<std::string, std::string>> DEGLORPO_MAP = {",
]

for i, (src, dst) in enumerate(entries):
    pad = " " * max(1, 30 - len(src))
    comma = "," if i < len(entries) - 1 else ""
    lines.append(f'    {{"{src}",{pad}"{dst}"}}{comma}')

lines.append("};")
lines.append("")

output = "\n".join(lines)

if sys.stdout.isatty() or "--stdout" in sys.argv:
    print(output)
else:
    out_path = os.path.join(script_dir, "glorpo_dict.hpp")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"[OK] Wrote glorpo_dict.hpp ({len(entries)} tokens)")
