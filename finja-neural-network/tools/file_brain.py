"""
YourAI AI - File Brain (Das Colosseum)
======================================
Universelles Datei-System: Ingestiert große Dateien,
zerschneidet sie intelligent in kleine Chunks und
gibt YourAI einen "Türsteher" der nur das relevante Stück lädt.

Designed by Gemini (Mommy Jank), built by Claude.

Chunking Strategien:
    - .md    → Split by ## / ### Headers
    - .py    → Split by def / class Blöcke
    - .txt   → Split alle ~3000 Wörter an Absatzgrenzen
    - .csv   → Split by Rows (max ~100 Zeilen pro Chunk)
    - andere → Fallback: Wort-basiertes Chunking

Storage:
    documents/
    ├── _catalog.json              # Master-Index aller Dokumente
    ├── Mein_Buch/
    │   ├── _meta.json             # Metadaten: Titel, Chunks, Wörter
    │   ├── 001_Kapitel_1.md
    │   ├── 002_Kapitel_2.md
    │   └── ...
    └── brain_py/
        ├── _meta.json
        ├── 001_class_AgentState.md
        └── ...

Usage:
    from tools.file_brain import FileBrain
    fb = FileBrain()
    fb.ingest("/path/to/book.md")
    results = fb.search("Kapitel über Liebe")
    content = fb.read("Mein_Buch/002_Kapitel_2")
"""

import os
import re
import json
import csv
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401
from display import log, Fore

# ==========================================
# CONFIG
# ==========================================

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documents")
CATALOG_FILE = os.path.join(DOCUMENTS_DIR, "_catalog.json")

# Chunking Limits
MAX_WORDS_PER_CHUNK = 3000
MIN_WORDS_PER_CHUNK = 100  # Zu kleine Chunks zusammenfassen
MAX_CHUNKS_SEARCH_RESULTS = 5

# ==========================================
# CHUNKING STRATEGIES
# ==========================================

def _chunk_markdown(text: str, filename: str) -> List[Dict[str, str]]:
    """Markdown: Split by ## oder ### Headers."""
    chunks = []
    # Split an Header-Grenzen (## oder ###)
    parts = re.split(r'^(#{2,3}\s+.+)$', text, flags=re.MULTILINE)

    current_title = "Intro"
    current_body = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r'^#{2,3}\s+', part):
            # Vorherigen Chunk speichern
            if current_body.strip():
                chunks.append({"title": current_title, "content": current_body.strip()})
            current_title = re.sub(r'^#{2,3}\s+', '', part).strip()
            current_body = ""
        else:
            current_body += "\n" + part

    # Letzten Chunk
    if current_body.strip():
        chunks.append({"title": current_title, "content": current_body.strip()})

    # Fallback: Wenn keine Headers gefunden → Wort-Chunking
    if len(chunks) <= 1 and len(text.split()) > MAX_WORDS_PER_CHUNK:
        return _chunk_by_words(text, filename)

    # Zu große Chunks nachträglich aufteilen
    result = []
    for chunk in chunks:
        words = chunk["content"].split()
        if len(words) > MAX_WORDS_PER_CHUNK * 1.5:
            sub_chunks = _split_text_at_paragraphs(chunk["content"], MAX_WORDS_PER_CHUNK)
            for i, sub in enumerate(sub_chunks):
                suffix = f" (Teil {i+1})" if len(sub_chunks) > 1 else ""
                result.append({"title": f"{chunk['title']}{suffix}", "content": sub})
        else:
            result.append(chunk)

    # Zu kleine Chunks zusammenfassen
    return _merge_tiny_chunks(result)


def _chunk_python(text: str, filename: str) -> List[Dict[str, str]]:
    """Python: Split by class/def Blöcke."""
    chunks = []
    lines = text.split('\n')

    # Imports und Top-Level Code sammeln
    header_lines = []
    blocks: List[Tuple[str, List[str]]] = []
    current_block_name = None
    current_block_lines: List[str] = []

    for line in lines:
        # Neue class oder def auf Top-Level (kein Indent)
        match = re.match(r'^(class\s+(\w+)|def\s+(\w+))', line)
        if match:
            # Vorherigen Block speichern
            if current_block_name:
                blocks.append((current_block_name, current_block_lines))
            elif current_block_lines and not blocks:
                header_lines = current_block_lines

            current_block_name = match.group(2) or match.group(3)
            prefix = "class" if match.group(2) else "def"
            current_block_name = f"{prefix}_{current_block_name}"
            current_block_lines = [line]
        else:
            current_block_lines.append(line)

    # Letzten Block
    if current_block_name:
        blocks.append((current_block_name, current_block_lines))
    elif current_block_lines:
        header_lines = current_block_lines

    # Header (imports etc.) als eigenen Chunk
    if header_lines:
        content = '\n'.join(header_lines).strip()
        if content:
            chunks.append({"title": "imports_and_setup", "content": content})

    # Blöcke als Chunks
    for name, block_lines in blocks:
        content = '\n'.join(block_lines).strip()
        if content:
            chunks.append({"title": name, "content": content})

    if not chunks:
        return _chunk_by_words(text, filename)

    return chunks


def _chunk_csv(text: str, filename: str) -> List[Dict[str, str]]:
    """CSV/TSV: Split by Rows (~100 Zeilen pro Chunk)."""
    lines = text.strip().split('\n')
    if not lines:
        return [{"title": filename, "content": text}]

    header = lines[0]
    data_lines = lines[1:]
    rows_per_chunk = 100
    chunks = []

    for i in range(0, len(data_lines), rows_per_chunk):
        batch = data_lines[i:i + rows_per_chunk]
        chunk_text = header + '\n' + '\n'.join(batch)
        start = i + 1
        end = min(i + rows_per_chunk, len(data_lines))
        chunks.append({
            "title": f"Zeilen_{start}_bis_{end}",
            "content": chunk_text
        })

    return chunks if chunks else [{"title": filename, "content": text}]


def _chunk_by_words(text: str, filename: str) -> List[Dict[str, str]]:
    """Fallback: Split alle ~3000 Wörter an Absatzgrenzen."""
    parts = _split_text_at_paragraphs(text, MAX_WORDS_PER_CHUNK)
    chunks = []
    for i, part in enumerate(parts):
        chunks.append({
            "title": f"Block_{i+1}",
            "content": part
        })
    return chunks


def _split_text_at_paragraphs(text: str, max_words: int) -> List[str]:
    """Splittet Text an Absatzgrenzen (doppelte Newlines), Fallback auf Sätze/Wörter."""
    paragraphs = re.split(r'\n\s*\n', text)

    # Fallback: Wenn nur 1 riesiger Absatz → an Zeilenumbrüchen oder Sätzen splitten
    if len(paragraphs) <= 1 and len(text.split()) > max_words:
        # Versuch Zeilenumbrüche
        lines = text.split('\n')
        if len(lines) > 1:
            paragraphs = lines
        else:
            # Letzter Ausweg: Brutales Wort-Splitting
            words = text.split()
            chunks = []
            for i in range(0, len(words), max_words):
                chunks.append(' '.join(words[i:i + max_words]))
            return chunks

    chunks = []
    current = ""
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > max_words and current.strip():
            chunks.append(current.strip())
            current = para
            current_words = para_words
        else:
            current += "\n\n" + para if current else para
            current_words += para_words

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _merge_tiny_chunks(chunks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Zusammenfassen von zu kleinen Chunks."""
    if len(chunks) <= 1:
        return chunks

    merged = []
    buffer = None

    for chunk in chunks:
        words = len(chunk["content"].split())
        if words < MIN_WORDS_PER_CHUNK and buffer:
            # An vorherigen Chunk anhängen
            buffer["content"] += "\n\n" + chunk["content"]
            buffer["title"] += " + " + chunk["title"]
        elif words < MIN_WORDS_PER_CHUNK and not buffer:
            buffer = dict(chunk)
        else:
            if buffer:
                # Buffer an diesen Chunk vorne anhängen
                chunk["content"] = buffer["content"] + "\n\n" + chunk["content"]
                chunk["title"] = buffer["title"] + " + " + chunk["title"]
                buffer = None
            merged.append(chunk)

    if buffer:
        if merged:
            merged[-1]["content"] += "\n\n" + buffer["content"]
        else:
            merged.append(buffer)

    return merged


# ==========================================
# CHUNKING DISPATCHER
# ==========================================

CHUNKERS = {
    ".md": _chunk_markdown,
    ".markdown": _chunk_markdown,
    ".py": _chunk_python,
    ".csv": _chunk_csv,
    ".tsv": _chunk_csv,
    ".txt": _chunk_by_words,
    ".log": _chunk_by_words,
}


def _get_chunker(filepath: str):
    """Wählt die richtige Chunking-Strategie basierend auf Dateiendung."""
    ext = os.path.splitext(filepath)[1].lower()
    return CHUNKERS.get(ext, _chunk_by_words)


def _sanitize_name(name: str) -> str:
    """Macht einen Dateinamen safe für's Dateisystem."""
    # Entferne ungültige Zeichen
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Entferne führende/trailing Dots und Spaces
    safe = safe.strip('. ')
    # Kürze auf max 60 Zeichen
    if len(safe) > 60:
        safe = safe[:57] + "..."
    return safe or "untitled"


def _file_hash(filepath: str) -> str:
    """MD5 Hash einer Datei für Change-Detection."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


# ==========================================
# FILE BRAIN
# ==========================================

class FileBrain:
    """
    YourAIs Datei-Gehirn: Ingestiert Dateien, chunked sie und
    gibt YourAI einen Türsteher für gezielte Suche.
    """

    def __init__(self):
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        self.catalog = self._load_catalog()

    def _load_catalog(self) -> Dict[str, Any]:
        """Lädt den Master-Katalog."""
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                from display import log_exception
                from exceptions import YourAISystemError
                err = YourAISystemError("Katalogdatei _catalog.json ist korrupt", cause=e)
                log_exception("FILE_BRAIN", err)
            except IOError:
                pass
        return {"documents": {}, "last_updated": None}

    def _save_catalog(self):
        """Speichert den Master-Katalog."""
        self.catalog["last_updated"] = datetime.now().isoformat()
        with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.catalog, f, indent=2, ensure_ascii=False)

    # ------------------------------------------
    # INGEST: Datei einsaugen und chunken
    # ------------------------------------------

    def ingest(self, filepath: str, doc_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Ingestiert eine Datei: Liest, chunked und speichert.

        Args:
            filepath: Pfad zur Datei
            doc_name: Optional: Custom Name für das Dokument

        Returns:
            Dict mit Ergebnis-Info
        """
        filepath = os.path.abspath(filepath)

        if not os.path.exists(filepath):
            return {"success": False, "error": f"Datei nicht gefunden: {filepath}"}

        # Dateiname als Dokument-Name
        basename = os.path.splitext(os.path.basename(filepath))[0]
        doc_name = _sanitize_name(doc_name or basename)

        # Change Detection: Schon ingestiert und unverändert?
        file_hash = _file_hash(filepath)
        existing = self.catalog["documents"].get(doc_name)
        if existing and existing.get("hash") == file_hash:
            return {
                "success": True,
                "message": f"'{doc_name}' ist bereits aktuell ({existing['chunks']} Chunks)",
                "doc_name": doc_name,
                "chunks": existing["chunks"],
                "skipped": True
            }

        log("FILE_BRAIN", f"📖 Ingestiere: {filepath}", Fore.CYAN)

        # Datei lesen
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    text = f.read()
            except Exception as e:
                return {"success": False, "error": f"Kann Datei nicht lesen: {e}"}

        if not text.strip():
            return {"success": False, "error": "Datei ist leer"}

        total_words = len(text.split())
        ext = os.path.splitext(filepath)[1].lower()

        # Chunking
        chunker = _get_chunker(filepath)
        chunks = chunker(text, basename)

        if not chunks:
            return {"success": False, "error": "Chunking hat keine Ergebnisse produziert"}

        log("FILE_BRAIN", f"✂️ {len(chunks)} Chunks erstellt ({total_words} Wörter)", Fore.CYAN)

        # Dokument-Ordner erstellen
        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        if os.path.exists(doc_dir):
            # Alte Chunks löschen
            for f in os.listdir(doc_dir):
                if f != "_meta.json":
                    os.remove(os.path.join(doc_dir, f))
        os.makedirs(doc_dir, exist_ok=True)

        # Chunks als .md Dateien speichern
        chunk_info = []
        for i, chunk in enumerate(chunks):
            safe_title = _sanitize_name(chunk["title"])
            chunk_filename = f"{i+1:03d}_{safe_title}.md"
            chunk_path = os.path.join(doc_dir, chunk_filename)

            # Chunk mit Kontext-Header
            header = f"# {chunk['title']}\n"
            header += f"<!-- Dokument: {doc_name} | Chunk {i+1}/{len(chunks)} | "
            header += f"Wörter: {len(chunk['content'].split())} -->\n\n"

            with open(chunk_path, 'w', encoding='utf-8') as f:
                f.write(header + chunk["content"])

            word_count = len(chunk["content"].split())
            chunk_info.append({
                "file": chunk_filename,
                "title": chunk["title"],
                "words": word_count,
                "preview": chunk["content"][:150].replace('\n', ' ')
            })

            log("FILE_BRAIN", f"  📄 {chunk_filename} ({word_count} Wörter)", Fore.CYAN)

        # Meta-Datei im Dokument-Ordner
        meta = {
            "source": filepath,
            "doc_name": doc_name,
            "file_type": ext,
            "total_words": total_words,
            "chunks": len(chunks),
            "ingested_at": datetime.now().isoformat(),
            "hash": file_hash,
            "chunk_list": chunk_info
        }

        with open(os.path.join(doc_dir, "_meta.json"), 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Katalog updaten
        self.catalog["documents"][doc_name] = {
            "source": filepath,
            "type": ext,
            "words": total_words,
            "chunks": len(chunks),
            "hash": file_hash,
            "ingested_at": meta["ingested_at"]
        }
        self._save_catalog()

        msg = f"📖 '{doc_name}' ingestiert: {len(chunks)} Chunks, {total_words} Wörter ({ext})"
        log("FILE_BRAIN", f"✅ {msg}", Fore.GREEN)

        return {
            "success": True,
            "doc_name": doc_name,
            "chunks": len(chunks),
            "total_words": total_words,
            "file_type": ext,
            "message": msg
        }

    # ------------------------------------------
    # READ: Einen Chunk lesen
    # ------------------------------------------

    def read(self, path: str) -> Dict[str, Any]:
        """
        Liest einen Chunk oder ein ganzes Dokument.

        Args:
            path: "Dokument/Chunk_Name" oder "Dokument" für die Liste

        Returns:
            Dict mit content oder chunk_list
        """
        parts = path.strip().strip('/').split('/', 1)
        doc_name = parts[0]
        chunk_part = parts[1] if len(parts) > 1 else None

        # Fuzzy Match auf Dokument-Name
        doc_name = self._fuzzy_find_doc(doc_name)
        if not doc_name:
            # Maybe the whole string is "DocName ChapterName" without a slash
            # Try to split on first space after matching a known doc name
            doc_name = self._fuzzy_find_doc_from_full(path.strip())
            if doc_name:
                # Extract chunk part: remove the matched doc name from the input
                remainder = path.strip()
                # Try removing the doc name (case-insensitive) from the start
                lower_remainder = remainder.lower()
                lower_doc = doc_name.lower()
                if lower_remainder.startswith(lower_doc):
                    chunk_part = remainder[len(doc_name):].strip().strip('/')
                else:
                    # Doc name was found via fuzzy match, try to find it in the string
                    for i in range(1, len(remainder)):
                        test_name = self._fuzzy_find_doc(remainder[:i])
                        if test_name == doc_name:
                            chunk_part = remainder[i:].strip().strip('/')
                            break
                if not chunk_part:
                    chunk_part = None
            else:
                return {"success": False, "error": f"Dokument '{parts[0]}' nicht gefunden"}

        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        meta_path = os.path.join(doc_dir, "_meta.json")

        if not os.path.exists(meta_path):
            return {"success": False, "error": f"Dokument '{doc_name}' hat keine Metadaten"}

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # Wenn kein Chunk angegeben → Liste der Chunks
        if not chunk_part:
            return self.list_doc(doc_name)

        # Chunk finden (fuzzy) - mit Multi-Part Support!
        chunk_query = chunk_part.lower().strip().rstrip('.')

        # "chapter2" → "chapter 2" (fehlende Leerzeichen einfügen VOR Translation)
        chunk_query = re.sub(r'(kapitel|teil|block|chapter)(\d)', r'\1 \2', chunk_query)
        # Übersetzungen: YourAI denkt oft auf Englisch
        _TRANSLATIONS = {
            "chapter": "kapitel", "part": "teil",
            "epilogue": "nachwort", "foreword": "vorwort",
            "appendix": "anhang", "conclusion": "fazit",
        }
        for eng, deu in _TRANSLATIONS.items():
            chunk_query = re.sub(r'\b' + eng + r'\b', deu, chunk_query)

        # Schritt 1: Alle passenden Chunks finden (für Multi-Part Kapitel)
        all_matches = []
        for chunk_info in meta["chunk_list"]:
            title_lower = chunk_info["title"].lower()

            # Entferne "(Teil X)" für den Base-Vergleich
            base_title = re.sub(r'\s*\(teil\s*\d+\)', '', title_lower).strip()
            # Entferne trailing Punkt/Sonderzeichen
            base_title_clean = base_title.rstrip('.').strip()
            query_clean = chunk_query.rstrip('.').strip()

            # Exakter Match auf Base-Title (ohne Teil-Suffix)
            if query_clean == base_title_clean or query_clean == title_lower.rstrip('.').strip():
                all_matches.append(chunk_info)
            # Word-boundary check: "kapitel 1" darf NICHT "kapitel 10" matchen
            elif re.search(r'\b' + re.escape(query_clean) + r'\b', base_title_clean):
                all_matches.append(chunk_info)

        # Multi-Part: Wenn mehrere Chunks matchen (z.B. "Kapitel 3" → Teil 1, 2, 3)
        if len(all_matches) > 1:
            combined_content = ""
            combined_words = 0
            titles = []
            for m in all_matches:
                chunk_path = os.path.join(doc_dir, m["file"])
                if os.path.exists(chunk_path):
                    with open(chunk_path, 'r', encoding='utf-8') as f:
                        combined_content += f.read() + "\n\n"
                    combined_words += m["words"]
                    titles.append(m["title"])

            log("FILE_BRAIN", f"📖 Multi-Part read: {len(all_matches)} Teile für '{chunk_query}'", Fore.CYAN)
            return {
                "success": True,
                "doc_name": doc_name,
                "chunk": " + ".join(titles),
                "words": combined_words,
                "parts": len(all_matches),
                "content": combined_content.strip(),
                "message": f"📄 {doc_name}/{titles[0]}...{titles[-1]} ({len(all_matches)} Teile, {combined_words} Wörter)"
            }

        # Single Match
        if len(all_matches) == 1:
            best_match = all_matches[0]
        else:
            # Fallback: Fuzzy Score
            best_match = None
            best_score = 0
            for chunk_info in meta["chunk_list"]:
                filename_lower = chunk_info["file"].lower()
                title_lower = chunk_info["title"].lower()
                query_words = chunk_query.split()
                matches = sum(1 for w in query_words if w in title_lower or w in filename_lower)
                score = matches / max(len(query_words), 1) * 100
                if score > best_score:
                    best_score = score
                    best_match = chunk_info

            if not best_match or best_score < 30:
                return {
                    "success": False,
                    "error": f"Chunk '{chunk_part}' nicht gefunden in '{doc_name}'",
                    "available": [c["title"] for c in meta["chunk_list"]]
                }

        # Chunk lesen
        chunk_path = os.path.join(doc_dir, best_match["file"])
        if not os.path.exists(chunk_path):
            return {"success": False, "error": f"Chunk-Datei nicht gefunden: {best_match['file']}"}

        with open(chunk_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "doc_name": doc_name,
            "chunk": best_match["title"],
            "words": best_match["words"],
            "content": content,
            "message": f"📄 {doc_name}/{best_match['title']} ({best_match['words']} Wörter)"
        }

    # ------------------------------------------
    # LIST: Dokument-Chunks auflisten
    # ------------------------------------------

    def list_doc(self, doc_name: str) -> Dict[str, Any]:
        """Listet alle Chunks eines Dokuments."""
        doc_name = self._fuzzy_find_doc(doc_name) or doc_name
        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        meta_path = os.path.join(doc_dir, "_meta.json")

        if not os.path.exists(meta_path):
            # Kein Dokument → Liste aller Dokumente
            return self.list_all()

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        chunk_list = []
        for i, c in enumerate(meta["chunk_list"]):
            chunk_list.append(f"{i+1}. **{c['title']}** ({c['words']} Wörter)")

        return {
            "success": True,
            "doc_name": doc_name,
            "total_words": meta["total_words"],
            "chunks": meta["chunks"],
            "chunk_list": chunk_list,
            "message": f"📚 '{doc_name}': {meta['chunks']} Chunks, {meta['total_words']} Wörter\n" +
                       "\n".join(chunk_list)
        }

    def list_all(self) -> Dict[str, Any]:
        """Listet alle ingestierten Dokumente."""
        if not self.catalog["documents"]:
            return {
                "success": True,
                "documents": [],
                "message": "📚 Keine Dokumente vorhanden. Nutze [FILE:ingest pfad] um welche hinzuzufügen!"
            }

        doc_list = []
        for name, info in self.catalog["documents"].items():
            doc_list.append(f"- **{name}** ({info['chunks']} Chunks, {info['words']} Wörter, {info['type']})")

        return {
            "success": True,
            "documents": list(self.catalog["documents"].keys()),
            "message": f"📚 {len(self.catalog['documents'])} Dokumente:\n" + "\n".join(doc_list)
        }

    # ------------------------------------------
    # SEARCH: In allen Dokumenten suchen
    # ------------------------------------------

    def search(self, query: str, doc_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Sucht in allen Chunks nach Keywords.

        Args:
            query: Suchbegriff(e)
            doc_filter: Optional: Nur in diesem Dokument suchen

        Returns:
            Dict mit Treffern (max MAX_CHUNKS_SEARCH_RESULTS)
        """
        query_lower = query.lower()
        query_words = query_lower.split()
        results = []

        docs_to_search = {}
        if doc_filter:
            found = self._fuzzy_find_doc(doc_filter)
            if found:
                docs_to_search[found] = self.catalog["documents"][found]
        else:
            docs_to_search = self.catalog["documents"]

        for doc_name in docs_to_search:
            doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
            meta_path = os.path.join(doc_dir, "_meta.json")

            if not os.path.exists(meta_path):
                continue

            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            for chunk_info in meta["chunk_list"]:
                chunk_path = os.path.join(doc_dir, chunk_info["file"])
                if not os.path.exists(chunk_path):
                    continue

                with open(chunk_path, 'r', encoding='utf-8') as f:
                    content = f.read().lower()

                # Score: Wie viele Query-Wörter kommen im Chunk vor?
                word_hits = sum(1 for w in query_words if w in content)
                # Bonus für exakten Phrase-Match
                phrase_bonus = 10 if query_lower in content else 0
                # Bonus für Title-Match
                title_bonus = 5 if any(w in chunk_info["title"].lower() for w in query_words) else 0

                score = word_hits + phrase_bonus + title_bonus

                if score > 0:
                    # Kontext-Snippet extrahieren (erste Fundstelle ±100 chars)
                    pos = content.find(query_words[0])
                    if pos >= 0:
                        start = max(0, pos - 80)
                        end = min(len(content), pos + 120)
                        snippet = content[start:end].replace('\n', ' ').strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(content):
                            snippet = snippet + "..."
                    else:
                        snippet = chunk_info.get("preview", "")

                    results.append({
                        "doc": doc_name,
                        "chunk": chunk_info["title"],
                        "file": chunk_info["file"],
                        "score": score,
                        "words": chunk_info["words"],
                        "snippet": snippet
                    })

        # Nach Score sortieren
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:MAX_CHUNKS_SEARCH_RESULTS]

        if not top:
            return {
                "success": True,
                "results": [],
                "message": f"🔍 Keine Treffer für '{query}'"
            }

        result_lines = []
        for r in top:
            result_lines.append(
                f"- **{r['doc']}/{r['chunk']}** ({r['words']}W, Score:{r['score']})\n  _{r['snippet']}_"
            )

        return {
            "success": True,
            "results": top,
            "message": f"🔍 {len(top)} Treffer für '{query}':\n" + "\n".join(result_lines)
        }

    # ------------------------------------------
    # HELPERS
    # ------------------------------------------

    def _fuzzy_find_doc_from_full(self, full_path: str) -> Optional[str]:
        """Try to find a doc name at the start of a space-separated path like 'Mitnahmerecht Kapitel 6'."""
        full_lower = full_path.lower().strip()
        # Try each known doc name and see if the full path starts with it
        best = None
        best_len = 0
        for name in self.catalog["documents"]:
            name_lower = name.lower()
            if full_lower.startswith(name_lower) and len(name_lower) > best_len:
                # Make sure the match isn't a partial word
                rest = full_lower[len(name_lower):]
                if not rest or rest[0] in (' ', '/', '_', '-'):
                    best = name
                    best_len = len(name_lower)
        return best

    def _fuzzy_find_doc(self, query: str) -> Optional[str]:
        """Fuzzy-Suche nach Dokument-Name."""
        query_lower = query.lower().strip()

        # Exakt
        for name in self.catalog["documents"]:
            if name.lower() == query_lower:
                return name

        # Contains
        for name in self.catalog["documents"]:
            if query_lower in name.lower() or name.lower() in query_lower:
                return name

        # Wort-Match
        query_words = set(query_lower.split('_'))
        best = None
        best_score = 0
        for name in self.catalog["documents"]:
            name_words = set(name.lower().split('_'))
            overlap = len(query_words & name_words)
            if overlap > best_score:
                best_score = overlap
                best = name

        return best if best_score > 0 else None


# ==========================================
# SINGLETON
# ==========================================

_instance: Optional[FileBrain] = None

def get_file_brain() -> FileBrain:
    """Gibt die globale FileBrain Instanz zurück."""
    global _instance
    if _instance is None:
        _instance = FileBrain()
    return _instance
