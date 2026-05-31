"""
YourAI AI - Glorpo Esolang
===========================
Eine esoterische Programmiersprache wo Python-Code wie absoluter
Nonsens aussieht, aber nativ funktioniert.

Inspiriert von Glorpo (Magic The Noah) - "Glorpo is pain."

Usage:
    from glorpo import glorpify, deglorpify, run_glp

    # Python → Glorpo
    glorpo_code = glorpify("def hello():\\n    print('hi')")
    # → "gloo hello():\\n    glorp('hi')"

    # Glorpo → Python
    python_code = deglorpify(glorpo_code)

    # .glp direkt ausführen
    run_glp("script.glp")
"""

import re
import sys
import os

# ==========================================
# 🧬 THE GLORPO DICTIONARY
# ==========================================
# Python keyword → Glorpo translation
# Regel: Alles klingt wie ein verrücktes Alien-Gremlin

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

    # --- Builtins ---
    "print":        "glorp",
    "input":        "glorpask",
    "len":          "glorpsize",
    "range":        "glorprange",
    "int":          "glorpnum",
    "str":          "glorptext",
    "float":        "glorpfloat",
    "list":         "glorplist",
    "dict":         "glorpmap",
    "set":          "glorpbag",
    "tuple":        "glorptuple",
    "bool":         "glorpbool",
    "type":         "glorptype",
    "isinstance":   "glorpisa",
    "enumerate":    "glorpcount",
    "zip":          "glorpzip",
    "map":          "glorpmorph",
    "filter":       "glorpsift",
    "sorted":       "glorpsort",
    "reversed":     "glorpflip",
    "abs":          "glorpabs",
    "min":          "glorpsmol",
    "max":          "glorpchonk",
    "sum":          "glorpsum",
    "any":          "glorpany",
    "all":          "glorpall",
    "open":         "glorpopen",
    "super":        "glorpsuper",
    "self":         "glorpself",
    "append":       "glorpshove",
    "pop":          "glorpyoink",
    "keys":         "glorpkeys",
    "values":       "glorpvals",
    "items":        "glorpstuff",
    "join":         "glorpglue",
    "split":        "glorpchop",
    "strip":        "glorptrim",
    "replace":      "glorpswap",
    "format":       "glorpfmt",
    "upper":        "glorpscream",
    "lower":        "glorpwhisper",
    "startswith":   "glorpbegin",
    "endswith":     "glorpend",
    "find":         "glorpseek",
    "count":        "glorptally",
    "index":        "glorpwhere",

    # --- Special ---
    "__init__":     "__glorpbirth__",
    "__str__":      "__glorpface__",
    "__repr__":     "__glorpmirror__",
    "__name__":     "__glorpname__",
    "__main__":     "__glorpmain__",
}

# Reverse dictionary für Deglorpification
DEGLORPO_DICT = {v: k for k, v in GLORPO_DICT.items()}

# Sortiert nach Länge (longest first) um Teilüberschneidungen zu vermeiden
_GLORPO_SORTED = sorted(GLORPO_DICT.items(), key=lambda x: len(x[0]), reverse=True)
_DEGLORPO_SORTED = sorted(DEGLORPO_DICT.items(), key=lambda x: len(x[0]), reverse=True)


# ==========================================
# 🔄 TRANSLATOR
# ==========================================

def _translate(code: str, mapping: list, reverse: bool = False) -> str:
    """
    Übersetzt Code Wort-für-Wort.
    - Normale Strings: überspringen
    - f-String {expressions}: WERDEN übersetzt
    - Comments: überspringen
    """
    result = []
    i = 0

    while i < len(code):
        # --- Strings (mit f-string Expression Support) ---
        if code[i] in ('"', "'"):
            quote_char = code[i]
            # Check ob f-string (f vor dem Quote)
            is_fstring = (i > 0 and code[i-1] == 'f')

            # Triple quote?
            if code[i:i+3] in ('"""', "'''"):
                end_quote = code[i:i+3]
                j = i + 3
                while j < len(code) and code[j:j+3] != end_quote:
                    if code[j] == '\\':
                        j += 1
                    elif is_fstring and code[j] == '{' and j+1 < len(code) and code[j+1] != '{':
                        # f-string expression: {expr} → übersetze den Inhalt
                        result.append(code[i:j+1])  # alles bis inkl. {
                        i = j + 1
                        depth = 1
                        expr_start = j + 1
                        while j + 1 < len(code) and depth > 0:
                            j += 1
                            if code[j] == '{': depth += 1
                            elif code[j] == '}': depth -= 1
                        # expr ist code[expr_start:j]
                        expr = code[expr_start:j]
                        result.append(_translate(expr, mapping, reverse))
                        result.append('}')
                        i = j + 1
                        continue
                    j += 1
                j += 3
                result.append(code[i:j])
                i = j
                continue
            else:
                j = i + 1
                while j < len(code) and code[j] != quote_char:
                    if code[j] == '\\':
                        j += 1
                    elif is_fstring and code[j] == '{' and j+1 < len(code) and code[j+1] != '{':
                        result.append(code[i:j+1])
                        i = j + 1
                        depth = 1
                        expr_start = j + 1
                        while j + 1 < len(code) and depth > 0:
                            j += 1
                            if code[j] == '{': depth += 1
                            elif code[j] == '}': depth -= 1
                        expr = code[expr_start:j]
                        result.append(_translate(expr, mapping, reverse))
                        result.append('}')
                        i = j + 1
                        continue
                    j += 1
                j += 1
                result.append(code[i:j])
                i = j
                continue

        # --- Comments überspringen ---
        if code[i] == '#':
            j = i
            while j < len(code) and code[j] != '\n':
                j += 1
            result.append(code[i:j])
            i = j
            continue

        # --- Wort-Boundary Check: Keyword ersetzen ---
        matched = False
        for src, dst in mapping:
            if code[i:i+len(src)] == src:
                # Wort-Boundary prüfen (kein Teil eines größeren Worts)
                before_ok = (i == 0 or not code[i-1].isalnum() and code[i-1] != '_')
                after_pos = i + len(src)
                after_ok = (after_pos >= len(code) or
                           not code[after_pos].isalnum() and code[after_pos] != '_')

                # Dunder-Methoden: boundary check anpassen
                if src.startswith('__') and src.endswith('__'):
                    before_ok = True
                    after_ok = True

                if before_ok and after_ok:
                    result.append(dst)
                    i += len(src)
                    matched = True
                    break

        if not matched:
            result.append(code[i])
            i += 1

    return "".join(result)


def glorpify(python_code: str) -> str:
    """Python-Code → Glorpo-Code übersetzen."""
    return _translate(python_code, _GLORPO_SORTED)


def deglorpify(glorpo_code: str) -> str:
    """Glorpo-Code → Python-Code zurückübersetzen."""
    return _translate(glorpo_code, _DEGLORPO_SORTED, reverse=True)


# ==========================================
# 🚀 .GLP RUNNER
# ==========================================

def run_glp(filepath: str, glorpo_globals: dict = None) -> None:
    """
    Führt eine .glp Datei aus.

    1. Liest die Datei
    2. Deglorpifiziert den Code
    3. exec() mit eigenem Namespace
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Glorpo file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        glorpo_code = f.read()

    python_code = deglorpify(glorpo_code)

    if glorpo_globals is None:
        glorpo_globals = {"__name__": "__main__", "__file__": filepath}

    # __glorpmain__ in Strings wird nicht deglorpifiziert (korrekt),
    # also prüfe ob der Code __glorpmain__ als String-Vergleich nutzt
    if '"__glorpmain__"' in python_code or "'__glorpmain__'" in python_code:
        glorpo_globals["__name__"] = "__glorpmain__"

    exec(python_code, glorpo_globals)


def run_glorpo_string(glorpo_code: str) -> str:
    """
    Führt Glorpo-Code als String aus und fängt stdout ab.
    Gibt den Output als String zurück.
    """
    import io
    from contextlib import redirect_stdout

    python_code = deglorpify(glorpo_code)
    output = io.StringIO()

    with redirect_stdout(output):
        exec(python_code, {"__name__": "__glorpmain__"})

    return output.getvalue()


# ==========================================
# 🧪 DEMO
# ==========================================

def _cli_main():
    """Entry point für `glorpo` CLI command."""
    import argparse

    parser = argparse.ArgumentParser(description="Glorpo Esolang - Glorpo is pain.")
    sub = parser.add_subparsers(dest="cmd")

    # glorpo run script.glp
    run_p = sub.add_parser("run", help="Execute a .glp file")
    run_p.add_argument("file", help="Path to .glp file")

    # glorpo translate script.py -> stdout als glorpo
    trans_p = sub.add_parser("translate", help="Python -> Glorpo")
    trans_p.add_argument("file", help="Path to .py file")
    trans_p.add_argument("-o", "--output", help="Output .glp file (default: stdout)")

    # glorpo reverse script.glp -> stdout als python
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
            print(f"Glorpified → {args.output}")
        else:
            print(result)

    elif args.cmd == "reverse":
        with open(args.file, "r", encoding="utf-8") as f:
            result = deglorpify(f.read())
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Deglorpified → {args.output}")
        else:
            print(result)

    elif args.cmd == "demo":
        demo = 'gloo fibonacci(n):\n    glorb n <= 1:\n        glorpback n\n    a, b = 0, 1\n    glorpach i glorpin glorprange(2, n + 1):\n        a, b = b, a + b\n    glorpback b\n\nglorpach i glorpin glorprange(10):\n    glorp(f"fib({i}) = {fibonacci(i)}")\n'
        print("=== GLORPO CODE ===")
        print(demo)
        print("=== EXECUTING ===")
        print(run_glorpo_string(demo))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli_main()
