"""
Glorpo Python Package
=====================
Translates between Python and Glorpo source code and executes .glp files.

Main Responsibilities:
- Maintain the Python-to-Glorpo token dictionary.
- Translate Python code to Glorpo and Glorpo code back to Python.
- Execute Glorpo files or strings with source-line context on errors.

Side Effects:
- Reads .glp files from disk when running scripts.
- Executes translated Python code through exec().
- Writes CLI output and translated files when requested.
"""

import re
import sys
import os

# ==========================================
# THE GLORPO DICTIONARY
# ==========================================
# Python keyword -> Glorpo translation.
# Rule: every token should sound like surreal alien syntax.

GLORPO_DICT = {
    # --- Control Flow ---
    "if":           "glorb",
    "elif":         "glorbelif",
    "else":         "glorpelse",
    "for":          "glorpach",
    "while":        "glorploop",
    "break":        "glorpsnap",
    "continue":     "glorpskip",
    "pass":         "glorpnull",
    "match":        "glorpcheck",
    "case":         "glorpwhen",

    # --- Functions / Classes ---
    "def":          "gloo",
    "return":       "glorpback",
    "class":        "glorpkin",
    "lambda":       "glorbda",
    "yield":        "glorpgive",
    "async":        "glorpfast",
    "await":        "glorpwait",

    # --- Variables / Values ---
    "True":         "glorpyes",
    "False":        "glorpno",
    "None":         "glorpvoid",
    "NotImplemented": "glorpnotyet",

    # --- Logic ---
    "and":          "glorpand",
    "or":           "glorpor",
    "not":          "glorpnot",
    "is":           "glorpis",
    "in":           "glorpin",

    # --- Imports ---
    "import":       "glorpget",
    "from":         "glorpfrom",
    "as":           "glorpas",

    # --- Error Handling ---
    "try":          "glorptry",
    "except":       "glorpcatch",
    "finally":      "glorpalways",
    "raise":        "glorpyeet",
    "assert":       "glorpswear",

    # --- Scope ---
    "global":       "glorpwide",
    "nonlocal":     "glorpreach",
    "del":          "glorpbye",
    "with":         "glorpwith",

    # --- Builtins: I/O & Conversion ---
    "print":        "glorp",
    "input":        "glorpask",
    "repr":         "glorpshow",
    "format":       "glorpfmt",
    "open":         "glorpopen",

    # --- Builtins: Types ---
    "int":          "glorpnum",
    "str":          "glorptext",
    "float":        "glorpfloat",
    "bool":         "glorpbool",
    "list":         "glorplist",
    "dict":         "glorpmap",
    "set":          "glorpbag",
    "tuple":        "glorptuple",
    "frozenset":    "glorpfrozen",
    "bytes":        "glorpbytes",
    "complex":      "glorpcomplex",
    "slice":        "glorpslice",
    "type":         "glorptype",
    "object":       "glorpthing",

    # --- Builtins: Inspection ---
    "len":          "glorpsize",
    "id":           "glorpid",
    "hash":         "glorphash",
    "dir":          "glorplook",
    "vars":         "glorpvars",
    "callable":     "glorpcall",
    "isinstance":   "glorpisa",
    "issubclass":   "glorpkidof",

    # --- Builtins: Attributes ---
    "hasattr":      "glorphas",
    "getattr":      "glorpgrab",
    "setattr":      "glorpset",
    "delattr":      "glorpdrop",
    "super":        "glorpsuper",
    "property":     "glorpprop",
    "staticmethod": "glorpstatic",
    "classmethod":  "glorpclassy",

    # --- Builtins: Iteration ---
    "range":        "glorprange",
    "enumerate":    "glorpcount",
    "zip":          "glorpzip",
    "map":          "glorpmorph",
    "filter":       "glorpsift",
    "sorted":       "glorpsort",
    "reversed":     "glorpflip",
    "iter":         "glorpwalk",
    "next":         "glorpnext",

    # --- Builtins: Math ---
    "abs":          "glorpabs",
    "min":          "glorpsmol",
    "max":          "glorpchonk",
    "sum":          "glorpsum",
    "round":        "glorpround",
    "pow":          "glorppow",
    "divmod":       "glorpdivmod",
    "hex":          "glorphex",
    "oct":          "glorpoct",
    "chr":          "glorpchr",
    "ord":          "glorpord",
    "bin":          "glorpbin",

    # --- Builtins: Logic ---
    "any":          "glorpany",
    "all":          "glorpall",

    # --- String Methods ---
    "split":        "glorpchop",
    "strip":        "glorptrim",
    "replace":      "glorpswap",
    "upper":        "glorpscream",
    "lower":        "glorpwhisper",
    "startswith":   "glorpbegin",
    "endswith":     "glorpend",
    "find":         "glorpseek",
    "count":        "glorptally",
    "index":        "glorpwhere",
    "join":         "glorpglue",

    # --- List / Dict Methods ---
    "append":       "glorpshove",
    "pop":          "glorpyoink",
    "keys":         "glorpkeys",
    "values":       "glorpvals",
    "items":        "glorpstuff",
    "self":         "glorpself",

    # --- Special ---
    "__init__":     "__glorpbirth__",
    "__str__":      "__glorpface__",
    "__repr__":     "__glorpmirror__",
    "__len__":      "__glorpsize__",
    "__iter__":     "__glorpwalk__",
    "__next__":     "__glorpstep__",
    "__enter__":    "__glorpcome__",
    "__exit__":     "__glorpleave__",
    "__call__":     "__glorpdo__",
    "__getitem__":  "__glorpgrab__",
    "__setitem__":  "__glorpput__",
    "__delitem__":  "__glorpzap__",
    "__contains__": "__glorpwithin__",
    "__name__":     "__glorpname__",
    "__main__":     "__glorpmain__",
    "__all__":      "__glorplist__",
    "__slots__":    "__glorpslots__",
    "__doc__":      "__glorpdoc__",
    "__class__":    "__glorpkind__",
    "__dict__":     "__glorpdata__",
}

# Reverse dictionary for deglorpification.
DEGLORPO_DICT = {v: k for k, v in GLORPO_DICT.items()}

# Sort longest-first to avoid partial overlaps.
_GLORPO_SORTED  = sorted(GLORPO_DICT.items(),  key=lambda x: len(x[0]), reverse=True)
_DEGLORPO_SORTED = sorted(DEGLORPO_DICT.items(), key=lambda x: len(x[0]), reverse=True)


# --- String-Scanner Helpers --------------------------------------------------

def _is_fstring_prefix(code: str, quote_pos: int) -> bool:
    """
    Detect if the quote at quote_pos is an f-string.
    Handles all prefix combinations: f, F, rf, fr, Rf, fR, RF, FR, etc.
    """
    prefix_chars: list[str] = []
    p = quote_pos - 1
    while p >= 0 and len(prefix_chars) < 2 and code[p].lower() in 'frbu':
        prefix_chars.insert(0, code[p].lower())
        p -= 1
    return 'f' in prefix_chars


def _scan_fstring_expr(code: str, open_brace: int, mapping: list) -> tuple:
    """
    Scans the f-string expression that starts right after '{' at open_brace.
    Handles nested braces.
    Returns (translated_expr: str, close_brace_pos: int).
    """
    depth = 1
    j = open_brace + 1
    expr_start = j
    while j < len(code) and depth > 0:
        if code[j] == '{':
            depth += 1
        elif code[j] == '}':
            depth -= 1
        if depth > 0:
            j += 1
    # j is now at the closing '}'
    expr = code[expr_start:j]
    return _translate(expr, mapping), j


def _scan_string(code: str, start: int, mapping: list, result: list) -> int:
    """
    Scans a string literal beginning at `start` (the opening quote char).
    Handles:
      - Triple and single quotes
      - Escape sequences
      - f-string {expressions} translated recursively
      - All f-string prefix variants: f, F, rf, fr, Rf, fR, RF, FR, ...
    Appends translated pieces to `result`.
    Returns the position immediately after the closing quote.
    """
    is_fstring = _is_fstring_prefix(code, start)

    # Triple or single quote?
    if code[start:start + 3] in ('"""', "'''"):
        end_seq = code[start:start + 3]
        seq_len = 3
    else:
        end_seq = code[start]
        seq_len = 1

    j = start + seq_len
    seg_start = start  # start of the current unprocessed raw segment

    while j < len(code):
        # End of string?
        if code[j:j + seq_len] == end_seq:
            result.append(code[seg_start:j + seq_len])
            return j + seq_len

        # Escape sequence - skip both chars
        if code[j] == '\\':
            j += 2
            continue

        # f-string expression: { ... }
        if is_fstring and code[j] == '{' and j + 1 < len(code) and code[j + 1] != '{':
            result.append(code[seg_start:j + 1])   # up to and including '{'
            translated, close_brace = _scan_fstring_expr(code, j, mapping)
            result.append(translated)
            result.append('}')
            j = close_brace + 1
            seg_start = j
            continue

        j += 1

    # Unclosed string - append remainder as-is
    result.append(code[seg_start:j])
    return j


# --- Core Translator ---------------------------------------------------------

def _translate(code: str, mapping: list, reverse: bool = False) -> str:
    """
    Translates code token-by-token using `mapping`.
      - String literals: content preserved, f-string expressions translated
      - Comments (#...): skipped as-is
      - Keywords: replaced only at proper word boundaries
    """
    result: list[str] = []
    i = 0

    while i < len(code):

        # --- String literal ---
        if code[i] in ('"', "'"):
            i = _scan_string(code, i, mapping, result)
            continue

        # --- Comment ---
        if code[i] == '#':
            j = i
            while j < len(code) and code[j] != '\n':
                j += 1
            result.append(code[i:j])
            i = j
            continue

        # --- Keyword / token substitution ---
        matched = False
        for src, dst in mapping:
            if code[i:i + len(src)] == src:
                # Word-boundary check
                before_ok = (
                    i == 0
                    or not (code[i - 1].isalnum() or code[i - 1] == '_')
                )
                after_pos = i + len(src)
                after_ok = (
                    after_pos >= len(code)
                    or not (code[after_pos].isalnum() or code[after_pos] == '_')
                )
                # Dunder names: skip boundary check (they include __ delimiters)
                if src.startswith('__') and src.endswith('__'):
                    before_ok = after_ok = True

                if before_ok and after_ok:
                    result.append(dst)
                    i += len(src)
                    matched = True
                    break

        if not matched:
            result.append(code[i])
            i += 1

    return ''.join(result)


def glorpify(python_code: str) -> str:
    """Translate Python code to Glorpo code."""
    return _translate(python_code, _GLORPO_SORTED)


def deglorpify(glorpo_code: str) -> str:
    """Translate Glorpo code back to Python code."""
    return _translate(glorpo_code, _DEGLORPO_SORTED, reverse=True)


# --- Traceback Helper --------------------------------------------------------

def _attach_glorpo_context(exc: Exception, glorpo_code: str, source_name: str) -> None:
    """
    Attaches the originating Glorpo source line to an exception (in-place),
    so tracebacks reference the Glorpo code instead of the deglorpified Python.
    Works with Python 3.11+ add_note(); falls back to args mutation otherwise.
    """
    import traceback as tb_module

    frames = tb_module.extract_tb(exc.__traceback__)
    glorpo_lines = glorpo_code.splitlines()

    for frame in reversed(frames):
        if frame.filename == '<string>':
            lineno = frame.lineno
            if 1 <= lineno <= len(glorpo_lines):
                glorpo_line = glorpo_lines[lineno - 1].strip()
                note = f"Glorpo source ({source_name}, line {lineno}): {glorpo_line}"
                if hasattr(exc, 'add_note'):   # Python 3.11+
                    exc.add_note(note)
                else:
                    orig = str(exc.args[0]) if exc.args else ''
                    exc.args = (f"{orig}\n{note}",) + exc.args[1:]
            break


# --- .GLP Runner -------------------------------------------------------------

def run_glp(filepath: str, glorpo_globals: dict = None) -> None:
    """
    Execute a .glp file.

    1. Read the file.
    2. Deglorpify the code.
    3. Execute it with an isolated namespace.
    4. Attach the Glorpo source line to tracebacks on errors.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Glorpo file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        glorpo_code = f.read()

    python_code = deglorpify(glorpo_code)

    if glorpo_globals is None:
        glorpo_globals = {"__name__": "__main__", "__file__": filepath}

    # __glorpmain__ inside strings is intentionally not deglorpified.
    # Check whether the code compares against __glorpmain__ as a string.
    if '"__glorpmain__"' in python_code or "'__glorpmain__'" in python_code:
        glorpo_globals["__name__"] = "__glorpmain__"

    try:
        exec(python_code, glorpo_globals)
    except Exception as exc:
        _attach_glorpo_context(exc, glorpo_code, filepath)
        raise


def run_glorpo_string(glorpo_code: str) -> str:
    """
    Execute Glorpo code from a string and capture stdout.
    Return the captured output as a string.
    Attach the Glorpo source line to tracebacks on errors.
    """
    import io
    from contextlib import redirect_stdout

    python_code = deglorpify(glorpo_code)
    output = io.StringIO()

    try:
        with redirect_stdout(output):
            exec(python_code, {"__name__": "__glorpmain__"})
    except Exception as exc:
        _attach_glorpo_context(exc, glorpo_code, "<string>")
        raise

    return output.getvalue()


# --- CLI ---------------------------------------------------------------------

def _cli_main():
    """Run the `glorpo` CLI command."""
    import argparse

    parser = argparse.ArgumentParser(description="Glorpo Esolang - Glorpo is pain.")
    sub = parser.add_subparsers(dest="cmd")

    # glorpo run script.glp
    run_p = sub.add_parser("run", help="Execute a .glp file")
    run_p.add_argument("file", help="Path to .glp file")

    # glorpo translate script.py -> stdout as Glorpo
    trans_p = sub.add_parser("translate", help="Python -> Glorpo")
    trans_p.add_argument("file", help="Path to .py file")
    trans_p.add_argument("-o", "--output", help="Output .glp file (default: stdout)")

    # glorpo reverse script.glp -> stdout as Python
    rev_p = sub.add_parser("reverse", help="Glorpo -> Python")
    rev_p.add_argument("file", help="Path to .glp file")
    rev_p.add_argument("-o", "--output", help="Output .py file (default: stdout)")

    # glorpo demo
    sub.add_parser("demo", help="Run the Glorpo demo")

    args = parser.parse_args()

    if args.cmd == "run":
        run_glp(args.file)

    elif args.cmd == "translate":
        with open(args.file, "r", encoding="utf-8") as f:
            result = glorpify(f.read())
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Glorpified -> {args.output}")
        else:
            print(result)

    elif args.cmd == "reverse":
        with open(args.file, "r", encoding="utf-8") as f:
            result = deglorpify(f.read())
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Deglorpified -> {args.output}")
        else:
            print(result)

    elif args.cmd == "demo":
        demo = (
            'gloo fibonacci(n):\n'
            '    glorb n <= 1:\n'
            '        glorpback n\n'
            '    a, b = 0, 1\n'
            '    glorpach i glorpin glorprange(2, n + 1):\n'
            '        a, b = b, a + b\n'
            '    glorpback b\n'
            '\n'
            'glorpach i glorpin glorprange(10):\n'
            '    glorp(f"fib({i}) = {fibonacci(i)}")\n'
        )
        print("=== GLORPO CODE ===")
        print(demo)
        print("=== EXECUTING ===")
        print(run_glorpo_string(demo))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli_main()
