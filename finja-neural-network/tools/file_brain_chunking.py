"""Chunking and filename helpers for YourAI's File Brain."""

import hashlib
import os
import re
from typing import Dict, List, Tuple

MAX_WORDS_PER_CHUNK = 3000
MIN_WORDS_PER_CHUNK = 100


def chunk_markdown(text: str, filename: str) -> List[Dict[str, str]]:
    """Markdown: split by ## or ### headers."""
    chunks = []
    parts = re.split(r'^(#{2,3}\s+.+)$', text, flags=re.MULTILINE)

    current_title = "Intro"
    current_body = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r'^#{2,3}\s+', part):
            if current_body.strip():
                chunks.append({"title": current_title, "content": current_body.strip()})
            current_title = re.sub(r'^#{2,3}\s+', '', part).strip()
            current_body = ""
        else:
            current_body += "\n" + part

    if current_body.strip():
        chunks.append({"title": current_title, "content": current_body.strip()})

    if len(chunks) <= 1 and len(text.split()) > MAX_WORDS_PER_CHUNK:
        return chunk_by_words(text, filename)

    result = []
    for chunk in chunks:
        words = chunk["content"].split()
        if len(words) > MAX_WORDS_PER_CHUNK * 1.5:
            sub_chunks = split_text_at_paragraphs(chunk["content"], MAX_WORDS_PER_CHUNK)
            for i, sub in enumerate(sub_chunks):
                suffix = f" (Part {i+1})" if len(sub_chunks) > 1 else ""
                result.append({"title": f"{chunk['title']}{suffix}", "content": sub})
        else:
            result.append(chunk)

    return merge_tiny_chunks(result)


def chunk_python(text: str, filename: str) -> List[Dict[str, str]]:
    """Python: split by top-level class/def blocks."""
    chunks = []
    lines = text.split('\n')

    header_lines = []
    blocks: List[Tuple[str, List[str]]] = []
    current_block_name = None
    current_block_lines: List[str] = []

    for line in lines:
        match = re.match(r'^(class\s+(\w+)|def\s+(\w+))', line)
        if match:
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

    if current_block_name:
        blocks.append((current_block_name, current_block_lines))
    elif current_block_lines:
        header_lines = current_block_lines

    if header_lines:
        content = '\n'.join(header_lines).strip()
        if content:
            chunks.append({"title": "imports_and_setup", "content": content})

    for name, block_lines in blocks:
        content = '\n'.join(block_lines).strip()
        if content:
            chunks.append({"title": name, "content": content})

    if not chunks:
        return chunk_by_words(text, filename)

    return chunks


def chunk_csv(text: str, filename: str) -> List[Dict[str, str]]:
    """CSV/TSV: split by rows."""
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
            "title": f"Rows_{start}_to_{end}",
            "content": chunk_text,
        })

    return chunks if chunks else [{"title": filename, "content": text}]


def chunk_by_words(text: str, filename: str) -> List[Dict[str, str]]:
    """Fallback: split around max word count at paragraph boundaries."""
    parts = split_text_at_paragraphs(text, MAX_WORDS_PER_CHUNK)
    return [{"title": f"Block_{i+1}", "content": part} for i, part in enumerate(parts)]


def split_text_at_paragraphs(text: str, max_words: int) -> List[str]:
    """Split text at paragraph boundaries, with line/word fallbacks."""
    paragraphs = re.split(r'\n\s*\n', text)

    if len(paragraphs) <= 1 and len(text.split()) > max_words:
        lines = text.split('\n')
        if len(lines) > 1:
            paragraphs = lines
        else:
            words = text.split()
            return [' '.join(words[i:i + max_words]) for i in range(0, len(words), max_words)]

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


def merge_tiny_chunks(chunks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge chunks that are too small into neighboring chunks."""
    if len(chunks) <= 1:
        return chunks

    merged = []
    buffer = None

    for chunk in chunks:
        words = len(chunk["content"].split())
        if words < MIN_WORDS_PER_CHUNK and buffer:
            buffer["content"] += "\n\n" + chunk["content"]
            buffer["title"] += " + " + chunk["title"]
        elif words < MIN_WORDS_PER_CHUNK and not buffer:
            buffer = dict(chunk)
        else:
            if buffer:
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


CHUNKERS = {
    ".md": chunk_markdown,
    ".markdown": chunk_markdown,
    ".py": chunk_python,
    ".csv": chunk_csv,
    ".tsv": chunk_csv,
    ".txt": chunk_by_words,
    ".log": chunk_by_words,
}


def get_chunker(filepath: str):
    """Choose chunking strategy by file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return CHUNKERS.get(ext, chunk_by_words)


def sanitize_name(name: str) -> str:
    """Make a safe filesystem name."""
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = safe.strip('. ')
    if len(safe) > 60:
        safe = safe[:57] + "..."
    return safe or "untitled"


def file_hash(filepath: str) -> str:
    """MD5 hash for change detection."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()
