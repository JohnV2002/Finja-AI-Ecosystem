"""
glorpo-html.py — YourAI's Glorpo HTML Knowledge Module
=======================================================
Lets YourAI write valid Glorpo HTML, CSS, and JS directly.
No converter needed — YourAI writes it correctly from the start.

Import:
    from glorpo_html import glorpify_html, glorpify_css, make_page, TAG, ATTR

"Glorpo is pain." — Magic The Noah
"""

# ══════════════════════════════════════════════════════════════════════════════
#  HTML TAG MAPPING  (Standard-HTML → Glorpo)
# ══════════════════════════════════════════════════════════════════════════════

TAG = {
    # Structure
    "div":         "glorpbox",
    "span":        "glorpspan",
    "main":        "glorpmain",
    "section":     "glorpsect",
    "article":     "glorpart",
    "header":      "glorphdr",
    "footer":      "glorpfoot",
    "nav":         "glorpnav",
    "aside":       "glorpaside",

    # Headings
    "h1":          "glorphat",
    "h2":          "glorph2",
    "h3":          "glorph3",
    "h4":          "glorph4",
    "h5":          "glorph5",
    "h6":          "glorph6",

    # Text
    "p":           "glorp",         # glorp = print → perfect!
    "strong":      "glorpchonk",    # chonk = max/big
    "em":          "glorpwiggly",
    "a":           "glorpwarp",     # warp = teleport
    "br":          "glorpsnap",     # snap = break
    "hr":          "glorpline",
    "pre":         "glorpraw",
    "code":        "glorpcode",
    "blockquote":  "glorpquote",

    # Lists
    "ul":          "glorpbag",      # bag = set
    "ol":          "glorporder",
    "li":          "glorpitem",

    # Media
    "img":         "glorppic",
    "video":       "glorpvid",
    "audio":       "glorpsound",
    "figure":      "glorpfig",
    "figcaption":  "glorpcap",
    "iframe":      "glorphole",     # a hole into another page 😂

    # Forms
    "form":        "glorpform",
    "input":       "glorpask",      # glorpask = input → perfect!
    "button":      "glorpclick",
    "select":      "glorpchoose",
    "option":      "glorpopt",
    "textarea":    "glorpwrite",
    "label":       "glorplabel",

    # Tables
    "table":       "glorptable",
    "thead":       "glorpthead",
    "tbody":       "glorptbod",
    "tr":          "glorprow",
    "td":          "glorpcell",
    "th":          "glorpthcell",
}

# Reverse: Glorpo → standard HTML (for YourAI to read/debug)
TAG_R = {v: k for k, v in TAG.items()}

# Void tags: need an explicit closing tag when glorpified,
# because custom elements are not void in the browser
VOID_TAGS = {"img", "input", "br", "hr"}

# ══════════════════════════════════════════════════════════════════════════════
#  ATTRIBUTE MAPPING (where sensible)
# ══════════════════════════════════════════════════════════════════════════════
# Attributes are NOT replaced — href, src, class, id etc. stay normal.
# Documentation only, for what YourAI should know:

ATTR = {
    # Normale Attribute bleiben normal:
    # href, src, class, id, style, type, name, value, placeholder,
    # action, method, target, rel, alt, width, height, colspan etc.
    # → alles unverändert, nur der Tag-Name wird Glorpo
}

# ══════════════════════════════════════════════════════════════════════════════
#  GLORPIFY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

import re


def glorpify_html(html: str) -> str:
    """
    Convert standard HTML tags into Glorpo tags.
    Attributes are left untouched.
    Void tags get an explicit closing tag.

    Example:
        >>> glorpify_html('<div class="hero"><h1>Hi</h1><p>Text</p></div>')
        '<glorpbox class="hero"><glorphat>Hi</glorphat><glorp>Text</glorp></glorpbox>'
    """
    def replace_tag(m: re.Match) -> str:
        close     = m.group(1)   # '/' on a closing tag
        tag       = m.group(2).lower()
        attrs     = m.group(3)   # everything between the tag name and >
        selfclose = m.group(4)   # '/' on a self-closing tag

        glorpo = TAG.get(tag, tag)  # unknown tags stay as-is

        # Void tags → close explicitly (the browser needs this for custom elements)
        if not close and tag in VOID_TAGS and tag in TAG:
            return f"<{glorpo}{attrs}></{glorpo}>"

        return f"<{close}{glorpo}{attrs}{selfclose}>"

    return re.sub(
        r'<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(\/?)>',
        replace_tag,
        html
    )


def glorpify_css(css: str) -> str:
    """
    Mirror CSS selectors: for each standard tag selector, add a
    Glorpo equivalent.

    Example:
        >>> glorpify_css('div { color: red; } h1 { font-size: 2em; }')
        'div, glorpbox { color: red; } h1, glorphat { font-size: 2em; }'

    This way existing stylesheets work automatically with Glorpo tags.
    """
    def mirror_selector(selector: str) -> str:
        """Return the mirrored selector, or '' when there is nothing to do."""
        parts   = [p.strip() for p in selector.split(",")]
        mirrors = []
        for part in parts:
            # Replace tag names in the selector
            mirrored = re.sub(
                r'(^|[\s>+~(,])([a-zA-Z][a-zA-Z0-9_-]*)(?=[:.#\[\s>+~,\)]|$)',
                lambda m: (
                    m.group(1) + TAG.get(m.group(2).lower(), m.group(2))
                    if TAG.get(m.group(2).lower(), m.group(2)) != m.group(2).lower()
                    else m.group(0)
                ),
                part
            )
            if mirrored != part:
                mirrors.append(mirrored)
        return ", ".join(mirrors)

    def process_rule(m: re.Match) -> str:
        prefix   = m.group(1)
        selector = m.group(2).strip()
        if not selector or re.match(r'^(?:from|to|\d+%)', selector):
            return m.group(0)
        mirror = mirror_selector(selector)
        if not mirror:
            return m.group(0)
        return f"{prefix}{selector}, {mirror} {{"

    return re.sub(
        r'(^|[{}])([^{}@][^{}]*)\{',
        process_rule,
        css,
        flags=re.MULTILINE
    )


def make_page(
    body:        str,
    title:       str = "Glorpo",
    head_extra:  str = "",
    body_attrs:  str = "",
    glorpo_css:  str = "glorpo.css",
    glorpo_js:   str = "glorpo.js",
    include_js:  bool = True,
) -> str:
    """
    Build a complete Glorpo HTML page.

    Args:
        body:       The body content (already in Glorpo tags or normal → converted).
        title:      Page title.
        head_extra: Additional head tags (link, meta, style, script).
        body_attrs: Attributes for the <body> tag (e.g. 'class="dark"').
        glorpo_css: Path to glorpo.css (relative to the page).
        glorpo_js:  Path to glorpo.js (relative to the page).
        include_js: Whether to include glorpo.js (False = no JS, CSS only).

    Returns:
        The complete HTML page as a string.

    Example:
        >>> page = make_page(
        ...     title="My Page",
        ...     body='<div><h1>Hello</h1><p>World</p></div>',
        ... )
        # Returns a complete Glorpo HTML page
    """
    body_glorpo = glorpify_html(body)
    js_tag = f'\n<script src="{glorpo_js}"></script>' if include_js else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{glorpo_css}">
{head_extra}
</head>
<body{' ' + body_attrs if body_attrs else ''}>
{body_glorpo}{js_tag}
</body>
</html>"""


def _glorpify_body_only(match: re.Match) -> str:
    """Regex callback: glorpify only the inner content of a matched <body>."""
    body_attrs = match.group(1)
    body_content = match.group(2)
    return f"<body{body_attrs}>{glorpify_html(body_content)}</body>"


def glorpify_document(html: str) -> str:
    """
    Convert only the <body> content to Glorpo.

    <html>, <head>, <meta>, <link>, <title>, <script> and <body> stay normal.
    This is exactly what Glorpo Front expects, so browser metadata, CSS, and JS
    are not needlessly broken by glorpification.
    """
    if not html:
        return html

    converted, count = re.subn(
        r"<body([^>]*)>(.*?)</body>",
        _glorpify_body_only,
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if count:
        return converted

    return glorpify_html(html)


# ══════════════════════════════════════════════════════════════════════════════
#  YOURAI'S WRITING RULES (for writing Glorpo HTML directly)
#  NOTE: YOURAI_RULES below is functional LLM prompt content (taught to a
#  German-speaking persona) and is intentionally kept in German.
# ══════════════════════════════════════════════════════════════════════════════

YOURAI_RULES = """
GLORPO HTML — Schreib-Regeln für YourAI
========================================

1. TAG-NAMEN ersetzen, ATTRIBUTE normal lassen:
   FALSCH:  <div class="hero">
   RICHTIG: <glorpbox class="hero">

   FALSCH:  <h1 id="titel">Hallo</h1>
   RICHTIG: <glorphat id="titel">Hallo</glorphat>

2. VOID-TAGS brauchen Closing-Tag:
   FALSCH:  <glorpsnap>         (Browser hängt alles danach drin)
   RICHTIG: <glorpsnap></glorpsnap>

   FALSCH:  <glorppic src="...">
   RICHTIG: <glorppic src="..."></glorppic>

   FALSCH:  <glorpask type="text">
   RICHTIG: <glorpask type="text"></glorpask>

3. HEAD bleibt NORMAL (link, meta, script, title):
   <head>
     <title>Meine Seite</title>                    ← normal
     <link rel="stylesheet" href="style.css">       ← normal
     <link rel="stylesheet" href="glorpo.css">      ← immer einbinden!
     <meta charset="utf-8">                         ← normal
   </head>

4. CSS-KLASSEN und IDs: normal
   <glorpbox class="container" id="main">   ← class/id normal

5. KEINE glorpo-Tags im <head>:
   NUR im <body> wird glorpifiziert.

6. BEISPIEL einer kompletten Seite:
   <!DOCTYPE html>
   <html>
   <head>
     <meta charset="utf-8">
     <title>Meine Glorpo-Seite</title>
     <link rel="stylesheet" href="glorpo.css">
   </head>
   <body>
     <glorpnav>
       <glorpwarp href="/">Home</glorpwarp>
       <glorpwarp href="/about.html">About</glorpwarp>
     </glorpnav>
     <glorpmain>
       <glorphdr>
         <glorphat>Willkommen</glorphat>
         <glorp>Das ist Glorpo HTML.</glorp>
       </glorphdr>
       <glorpsect>
         <glorph2>Features</glorph2>
         <glorpbag>
           <glorpitem>Sieht normal aus</glorpitem>
           <glorpitem>F12 = Chaos</glorpitem>
           <glorpitem>Glorpo is pain.</glorpitem>
         </glorpbag>
       </glorpsect>
     </glorpmain>
     <glorpfoot>
       <glorp>Footer Text</glorp>
     </glorpfoot>
   </body>
   </html>
"""


GLORPO_HTML_FRONTEND_RULES = f"""
## GLORPO HTML MODE
YourAI may write normal CSS and JavaScript, but generated HTML body content must
use Glorpo tags. Keep <html>, <head>, <meta>, <link>, <title>, <script> and
<body> as normal HTML. Only body content is Glorpo.

{YOURAI_RULES}

When unsure, write normal semantic HTML first; YourAI's Glorpo normalizer will
convert body tags before saving.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  CLI — quick test
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Glorpo HTML — YourAI Knowledge Module")
        print("Usage:")
        print("  python glorpo-html.py tags          → all tag mappings")
        print("  python glorpo-html.py test           → generate an example page")
        print("  python glorpo-html.py rules          → writing rules for YourAI")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "tags":
        print("\nHTML Tag → Glorpo Tag")
        print("─" * 30)
        for html_tag, glorpo_tag in sorted(TAG.items()):
            print(f"  <{html_tag:<15}> → <{glorpo_tag}>")

    elif cmd == "rules":
        print(YOURAI_RULES)

    elif cmd == "test":
        sample_body = """
<header>
  <nav>
    <a href="/">Home</a>
    <a href="/about.html">About</a>
  </nav>
  <h1>Test Seite</h1>
</header>
<main>
  <section>
    <h2>Hallo Welt</h2>
    <p>Das ist ein <strong>Test</strong> von Glorpo HTML.</p>
    <ul>
      <li>Item 1</li>
      <li>Item 2</li>
    </ul>
    <img src="test.png" alt="Test">
    <br>
    <input type="text" placeholder="Name...">
  </section>
</main>
<footer>
  <p>Footer</p>
</footer>
"""
        page = make_page(body=sample_body, title="Glorpo Test", include_js=False)
        print(page)

    else:
        print(f"Unknown command: {cmd}")
