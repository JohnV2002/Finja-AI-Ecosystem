"""
YourAI AI - File Brain (The Colosseum)
======================================
Universal file system: ingests large files, splits them intelligently into
small chunks, and gives YourAI a "bouncer" that loads only the relevant piece.

Designed by Gemini (Mommy Jank), built by Claude.

Chunking strategies:
    - .md    -> split by ## / ### headers
    - .py    -> split by def / class blocks
    - .txt   -> split every ~3000 words at paragraph boundaries
    - .csv   -> split by rows (max ~100 rows per chunk)
    - other  -> fallback: word-based chunking

Storage:
    documents/
    ├── _catalog.json              # master index of all documents
    ├── My_Book/
    │   ├── _meta.json             # metadata: title, chunks, words
    │   ├── 001_Chapter_1.md
    │   ├── 002_Chapter_2.md
    │   └── ...
    └── brain_py/
        ├── _meta.json
        ├── 001_class_AgentState.md
        └── ...

Usage:
    from tools.file_brain import FileBrain
    fb = FileBrain()
    fb.ingest("/path/to/book.md")
    results = fb.search("chapter about love")
    content = fb.read("My_Book/002_Chapter_2")
"""

import os
import re
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401
from display import log, log_exception, Fore
from exceptions import YourAISystemError
from tools.file_brain_chunking import (
    file_hash,
    get_chunker,
    sanitize_name,
)

# ==========================================
# CONFIG
# ==========================================

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documents")
CATALOG_FILE = os.path.join(DOCUMENTS_DIR, "_catalog.json")

# Chunking limits
MAX_WORDS_PER_CHUNK = 3000
MIN_WORDS_PER_CHUNK = 100  # Merge chunks that are too small
MAX_CHUNKS_SEARCH_RESULTS = 5

# ==========================================
# FILE BRAIN
# ==========================================

class FileBrain:
    """
    YourAI's file brain: ingests files, chunks them, and gives YourAI a
    bouncer for targeted search.
    """

    def __init__(self):
        """Ensure the documents directory exists and load the catalog."""
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        self.catalog = self._load_catalog()

    def _load_catalog(self) -> Dict[str, Any]:
        """Load the master catalog (empty structure if missing/corrupt)."""
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                err = YourAISystemError("Catalog file _catalog.json is corrupt", cause=e)
                log_exception("FILE_BRAIN", err)
            except IOError as e:
                err = YourAISystemError("Catalog file _catalog.json could not be read", cause=e)
                log_exception("FILE_BRAIN", err)
        return {"documents": {}, "last_updated": None}

    def _save_catalog(self):
        """Persist the master catalog to disk."""
        self.catalog["last_updated"] = datetime.now().isoformat()
        with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.catalog, f, indent=2, ensure_ascii=False)

    def _normalize_owner(self, owner_user_id: Optional[str]) -> str:
        """Stable owner key for per-user document isolation. Legacy docs belong to admin."""
        raw = (owner_user_id or "admin").strip().lower()
        safe = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("_")
        return safe[:80] or "admin"

    def _doc_owner(self, name: str, info: Optional[Dict[str, Any]] = None) -> str:
        """Return the normalized owner key for a catalog document."""
        info = info or self.catalog.get("documents", {}).get(name, {})
        return self._normalize_owner(info.get("owner_user_id") or info.get("owner") or "admin")

    def _is_visible_doc(self, name: str, owner_user_id: Optional[str]) -> bool:
        """Return True if a document is visible to the given owner (or is shared/public)."""
        owner = self._doc_owner(name)
        current = self._normalize_owner(owner_user_id)
        return owner in {"public", "shared", "__shared__"} or owner == current

    def _visible_documents(self, owner_user_id: Optional[str]) -> Dict[str, Any]:
        """Return the subset of catalog documents visible to the given owner."""
        return {
            name: info
            for name, info in self.catalog.get("documents", {}).items()
            if self._is_visible_doc(name, owner_user_id)
        }

    # ------------------------------------------
    # INGEST: read and chunk a file
    # ------------------------------------------

    def ingest(self, filepath: str, doc_name: Optional[str] = None, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Ingest a file: read it, chunk it, and store it.

        Args:
            filepath (str): Path to the file.
            doc_name (Optional[str]): Optional custom name for the document.
            owner_user_id (Optional[str]): Owner for per-user isolation.

        Returns:
            Dict[str, Any]: Result info.
        """
        filepath = os.path.abspath(filepath)

        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}

        # Filename as document name
        basename = os.path.splitext(os.path.basename(filepath))[0]
        doc_name = sanitize_name(doc_name or basename)
        owner_key = self._normalize_owner(owner_user_id)

        existing_for_name = self.catalog["documents"].get(doc_name)
        if existing_for_name and self._doc_owner(doc_name, existing_for_name) != owner_key:
            base_name = doc_name
            owner_suffix = sanitize_name(owner_key)
            candidate = sanitize_name(f"{base_name}_{owner_suffix}")
            counter = 2
            while (
                candidate in self.catalog["documents"]
                and self._doc_owner(candidate) != owner_key
            ):
                candidate = sanitize_name(f"{base_name}_{owner_suffix}_{counter}")
                counter += 1
            doc_name = candidate

        # Change detection: already ingested and unchanged?
        file_digest = file_hash(filepath)
        existing = self.catalog["documents"].get(doc_name)
        if existing and existing.get("hash") == file_digest and self._doc_owner(doc_name, existing) == owner_key:
            return {
                "success": True,
                "message": f"'{doc_name}' is already up to date ({existing['chunks']} chunks)",
                "doc_name": doc_name,
                "chunks": existing["chunks"],
                "owner_user_id": owner_key,
                "skipped": True
            }

        log("FILE_BRAIN", f"📖 Ingesting: {filepath}", Fore.CYAN)

        # Read file
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    text = f.read()
            except Exception as e:
                return {"success": False, "error": f"Cannot read file: {e}"}

        if not text.strip():
            return {"success": False, "error": "File is empty"}

        total_words = len(text.split())
        ext = os.path.splitext(filepath)[1].lower()

        # Chunking
        chunker = get_chunker(filepath)
        chunks = chunker(text, basename)

        if not chunks:
            return {"success": False, "error": "Chunking produced no results"}

        log("FILE_BRAIN", f"✂️ {len(chunks)} chunks created ({total_words} words)", Fore.CYAN)

        # Create document folder
        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        if os.path.exists(doc_dir):
            # Delete old chunks
            for f in os.listdir(doc_dir):
                if f != "_meta.json":
                    os.remove(os.path.join(doc_dir, f))
        os.makedirs(doc_dir, exist_ok=True)

        # Save chunks as .md files
        chunk_info = []
        for i, chunk in enumerate(chunks):
            safe_title = sanitize_name(chunk["title"])
            chunk_filename = f"{i+1:03d}_{safe_title}.md"
            chunk_path = os.path.join(doc_dir, chunk_filename)

            # Chunk with context header
            header = f"# {chunk['title']}\n"
            header += f"<!-- Document: {doc_name} | Chunk {i+1}/{len(chunks)} | "
            header += f"Words: {len(chunk['content'].split())} -->\n\n"

            with open(chunk_path, 'w', encoding='utf-8') as f:
                f.write(header + chunk["content"])

            word_count = len(chunk["content"].split())
            chunk_info.append({
                "file": chunk_filename,
                "title": chunk["title"],
                "words": word_count,
                "preview": chunk["content"][:150].replace('\n', ' ')
            })

            log("FILE_BRAIN", f"  📄 {chunk_filename} ({word_count} words)", Fore.CYAN)

        # Meta file in the document folder
        meta = {
            "source": filepath,
            "doc_name": doc_name,
            "file_type": ext,
            "total_words": total_words,
            "chunks": len(chunks),
            "ingested_at": datetime.now().isoformat(),
            "hash": file_digest,
            "owner_user_id": owner_key,
            "chunk_list": chunk_info
        }

        with open(os.path.join(doc_dir, "_meta.json"), 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Update catalog
        self.catalog["documents"][doc_name] = {
            "source": filepath,
            "type": ext,
            "words": total_words,
            "chunks": len(chunks),
            "hash": file_digest,
            "owner_user_id": owner_key,
            "ingested_at": meta["ingested_at"]
        }
        self._save_catalog()

        msg = f"📖 '{doc_name}' ingested: {len(chunks)} chunks, {total_words} words ({ext})"
        log("FILE_BRAIN", f"✅ {msg}", Fore.GREEN)

        return {
            "success": True,
            "doc_name": doc_name,
            "chunks": len(chunks),
            "total_words": total_words,
            "file_type": ext,
            "owner_user_id": owner_key,
            "message": msg
        }

    # ------------------------------------------
    # READ: read one chunk
    # ------------------------------------------

    def read(self, path: str, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Read a chunk or a whole document.

        Args:
            path (str): "Document/Chunk_Name" or "Document" for the listing.
            owner_user_id (Optional[str]): Owner for visibility checks.

        Returns:
            Dict[str, Any]: Dict with content or chunk_list.
        """
        parts = path.strip().strip('/').split('/', 1)
        doc_name = parts[0]
        chunk_part = parts[1] if len(parts) > 1 else None

        # Fuzzy match on document name
        doc_name = self._fuzzy_find_doc(doc_name, owner_user_id=owner_user_id)
        if not doc_name:
            # Maybe the whole string is "DocName ChapterName" without a slash
            # Try to split on first space after matching a known doc name
            doc_name = self._fuzzy_find_doc_from_full(path.strip(), owner_user_id=owner_user_id)
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
                        test_name = self._fuzzy_find_doc(remainder[:i], owner_user_id=owner_user_id)
                        if test_name == doc_name:
                            chunk_part = remainder[i:].strip().strip('/')
                            break
                if not chunk_part:
                    chunk_part = None
            else:
                return {"success": False, "error": f"Document '{parts[0]}' not found"}

        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        meta_path = os.path.join(doc_dir, "_meta.json")

        if not os.path.exists(meta_path):
            return {"success": False, "error": f"Document '{doc_name}' has no metadata"}

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # If no chunk specified -> list of chunks
        if not chunk_part:
            return self.list_doc(doc_name, owner_user_id=owner_user_id)

        # Find chunk (fuzzy) - with multi-part support!
        chunk_query = chunk_part.lower().strip().rstrip('.')

        # "chapter2" -> "chapter 2" (insert missing spaces BEFORE translation)
        chunk_query = re.sub(r'(kapitel|teil|block|chapter)(\d)', r'\1 \2', chunk_query)
        # Translations: YourAI often thinks in English (maps to German chunk titles)
        _TRANSLATIONS = {
            "chapter": "kapitel", "part": "teil",
            "epilogue": "nachwort", "foreword": "vorwort",
            "appendix": "anhang", "conclusion": "fazit",
        }
        for eng, deu in _TRANSLATIONS.items():
            chunk_query = re.sub(r'\b' + eng + r'\b', deu, chunk_query)

        # Step 1: find all matching chunks (for multi-part chapters)
        all_matches = []
        for chunk_info in meta["chunk_list"]:
            title_lower = chunk_info["title"].lower()

            # Remove "(Teil X)" for the base comparison
            base_title = re.sub(r'\s*\(teil\s*\d+\)', '', title_lower).strip()
            # Remove trailing dot/special chars
            base_title_clean = base_title.rstrip('.').strip()
            query_clean = chunk_query.rstrip('.').strip()

            # Exact match on base title (without part suffix)
            if query_clean == base_title_clean or query_clean == title_lower.rstrip('.').strip():
                all_matches.append(chunk_info)
            # Word-boundary check: "kapitel 1" must NOT match "kapitel 10"
            elif re.search(r'\b' + re.escape(query_clean) + r'\b', base_title_clean):
                all_matches.append(chunk_info)

        # Multi-part: if several chunks match (e.g. "Kapitel 3" -> part 1, 2, 3)
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

            log("FILE_BRAIN", f"📖 Multi-part read: {len(all_matches)} parts for '{chunk_query}'", Fore.CYAN)
            return {
                "success": True,
                "doc_name": doc_name,
                "chunk": " + ".join(titles),
                "words": combined_words,
                "parts": len(all_matches),
                "content": combined_content.strip(),
                "message": f"📄 {doc_name}/{titles[0]}...{titles[-1]} ({len(all_matches)} parts, {combined_words} words)"
            }

        # Single match
        if len(all_matches) == 1:
            best_match = all_matches[0]
        else:
            # Fallback: fuzzy score
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
                    "error": f"Chunk '{chunk_part}' not found in '{doc_name}'",
                    "available": [c["title"] for c in meta["chunk_list"]]
                }

        # Read chunk
        chunk_path = os.path.join(doc_dir, best_match["file"])
        if not os.path.exists(chunk_path):
            return {"success": False, "error": f"Chunk file not found: {best_match['file']}"}

        with open(chunk_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "doc_name": doc_name,
            "chunk": best_match["title"],
            "words": best_match["words"],
            "content": content,
            "message": f"📄 {doc_name}/{best_match['title']} ({best_match['words']} words)"
        }

    # ------------------------------------------
    # LIST: list document chunks
    # ------------------------------------------

    def list_doc(self, doc_name: str, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
        """List all chunks of a document."""
        doc_name = self._fuzzy_find_doc(doc_name, owner_user_id=owner_user_id) or doc_name
        doc_dir = os.path.join(DOCUMENTS_DIR, doc_name)
        meta_path = os.path.join(doc_dir, "_meta.json")

        if not os.path.exists(meta_path):
            # No document -> list all documents
            return self.list_all(owner_user_id=owner_user_id)

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        chunk_list = []
        for i, c in enumerate(meta["chunk_list"]):
            chunk_list.append(f"{i+1}. **{c['title']}** ({c['words']} words)")

        return {
            "success": True,
            "doc_name": doc_name,
            "total_words": meta["total_words"],
            "chunks": meta["chunks"],
            "chunk_list": chunk_list,
            "message": f"📚 '{doc_name}': {meta['chunks']} chunks, {meta['total_words']} words\n" +
                       "\n".join(chunk_list)
        }

    def list_all(self, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
        """List all ingested documents."""
        visible_docs = self._visible_documents(owner_user_id)
        if not visible_docs:
            return {
                "success": True,
                "documents": [],
                "message": "📚 No documents available. Use [FILE:ingest path] to add some!"
            }

        doc_list = []
        for name, info in visible_docs.items():
            doc_list.append(f"- **{name}** ({info['chunks']} chunks, {info['words']} words, {info['type']})")

        return {
            "success": True,
            "documents": list(visible_docs.keys()),
            "message": f"📚 {len(visible_docs)} documents:\n" + "\n".join(doc_list)
        }

    # ------------------------------------------
    # SEARCH: search across all documents
    # ------------------------------------------

    def search(self, query: str, doc_filter: Optional[str] = None, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Search all chunks for keywords.

        Args:
            query (str): Search term(s).
            doc_filter (Optional[str]): Optional: search only this document.
            owner_user_id (Optional[str]): Owner for visibility checks.

        Returns:
            Dict[str, Any]: Dict with hits (max MAX_CHUNKS_SEARCH_RESULTS).
        """
        query_lower = query.lower()
        query_words = query_lower.split()
        results = []

        docs_to_search = {}
        if doc_filter:
            found = self._fuzzy_find_doc(doc_filter, owner_user_id=owner_user_id)
            if found:
                docs_to_search[found] = self.catalog["documents"][found]
        else:
            docs_to_search = self._visible_documents(owner_user_id)

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

                # Score: how many query words appear in the chunk?
                word_hits = sum(1 for w in query_words if w in content)
                # Bonus for exact phrase match
                phrase_bonus = 10 if query_lower in content else 0
                # Bonus for title match
                title_bonus = 5 if any(w in chunk_info["title"].lower() for w in query_words) else 0

                score = word_hits + phrase_bonus + title_bonus

                if score > 0:
                    # Extract a context snippet (first hit ±100 chars)
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

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:MAX_CHUNKS_SEARCH_RESULTS]

        if not top:
            return {
                "success": True,
                "results": [],
                "message": f"🔍 No hits for '{query}'"
            }

        result_lines = []
        for r in top:
            result_lines.append(
                f"- **{r['doc']}/{r['chunk']}** ({r['words']}W, score:{r['score']})\n  _{r['snippet']}_"
            )

        return {
            "success": True,
            "results": top,
            "message": f"🔍 {len(top)} hits for '{query}':\n" + "\n".join(result_lines)
        }

    # ------------------------------------------
    # HELPERS
    # ------------------------------------------

    def _fuzzy_find_doc_from_full(self, full_path: str, owner_user_id: Optional[str] = None) -> Optional[str]:
        """Try to find a doc name at the start of a space-separated path like 'Mitnahmerecht Kapitel 6'."""
        full_lower = full_path.lower().strip()
        # Try each known doc name and see if the full path starts with it
        best = None
        best_len = 0
        for name in self._visible_documents(owner_user_id):
            name_lower = name.lower()
            if full_lower.startswith(name_lower) and len(name_lower) > best_len:
                # Make sure the match isn't a partial word
                rest = full_lower[len(name_lower):]
                if not rest or rest[0] in (' ', '/', '_', '-'):
                    best = name
                    best_len = len(name_lower)
        return best

    def _fuzzy_find_doc(self, query: str, owner_user_id: Optional[str] = None) -> Optional[str]:
        """Fuzzy search for a document name."""
        query_lower = query.lower().strip()
        visible_docs = self._visible_documents(owner_user_id)

        # Exact
        for name in visible_docs:
            if name.lower() == query_lower:
                return name

        # Contains
        for name in visible_docs:
            if query_lower in name.lower() or name.lower() in query_lower:
                return name

        # Word match
        query_words = set(query_lower.split('_'))
        best = None
        best_score = 0
        for name in visible_docs:
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
    """Return the global FileBrain instance (creating it on first use)."""
    global _instance
    if _instance is None:
        _instance = FileBrain()
    return _instance
