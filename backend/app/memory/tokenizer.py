"""Small dependency-free tokenizer used by memory search."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./:#@+-]{2,}")

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "for", "from", "had", "has", "have", "he", "her", "hers", "him",
    "his", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "ours", "she", "so", "that", "the",
    "their", "theirs", "them", "they", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "will",
    "with", "you", "your", "yours",
}


def tokenize(text: str, *, remove_stop_words: bool = True) -> list[str]:
    tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text or "")]
    if remove_stop_words:
        tokens = [token for token in tokens if token not in STOP_WORDS]
    return tokens


def term_frequencies(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def unique_terms(parts: Iterable[str]) -> set[str]:
    terms: set[str] = set()
    for part in parts:
        terms.update(tokenize(part))
    return terms
