from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(slots=True)
class TextChunk:
    ordinal: int
    content: str
    token_count: int

def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 180) -> list[TextChunk]:
    text = text.strip()
    if not text: return []
    if overlap < 0 or overlap >= chunk_size: raise ValueError("overlap must be >= 0 and smaller than chunk_size")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            pieces.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + chunk_size)
            if end < len(paragraph):
                boundary = max(paragraph.rfind(". ", start, end), paragraph.rfind("\n", start, end), paragraph.rfind(" ", start, end))
                if boundary > start + chunk_size // 2: end = boundary + 1
            pieces.append(paragraph[start:end].strip())
            if end >= len(paragraph): break
            start = max(start + 1, end - overlap)
    chunks: list[TextChunk] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else current + "\n\n" + piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current: chunks.append(TextChunk(len(chunks), current, estimate_tokens(current)))
            prefix = current[-overlap:] if current and overlap else ""
            current = (prefix + "\n" + piece).strip() if prefix else piece
            while len(current) > chunk_size:
                segment = current[:chunk_size]
                chunks.append(TextChunk(len(chunks), segment, estimate_tokens(segment)))
                current = current[max(1, chunk_size-overlap):]
    if current: chunks.append(TextChunk(len(chunks), current, estimate_tokens(current)))
    return chunks
