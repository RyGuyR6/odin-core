"""Dependency-free extractive summarization."""

from __future__ import annotations

import re
from collections import Counter

from app.memory.tokenizer import tokenize


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")


class ExtractiveSummarizer:
    def summarize(
        self,
        text: str,
        *,
        max_sentences: int = 4,
        max_characters: int = 1000,
    ) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_characters:
            return cleaned

        sentences = [
            sentence.strip()
            for sentence in SENTENCE_PATTERN.split(cleaned)
            if sentence.strip()
        ]
        if not sentences:
            return cleaned[:max_characters].rstrip()

        frequencies = Counter(tokenize(cleaned))
        if not frequencies:
            return cleaned[:max_characters].rstrip()

        scored: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            tokens = tokenize(sentence)
            if not tokens:
                continue
            lexical = sum(frequencies[token] for token in tokens) / len(tokens)
            position = 1.0 / (1.0 + index * 0.15)
            length_penalty = 1.0 if 40 <= len(sentence) <= 300 else 0.75
            scored.append((lexical * position * length_penalty, index, sentence))

        chosen = sorted(
            sorted(scored, reverse=True)[:max_sentences],
            key=lambda item: item[1],
        )

        summary = " ".join(sentence for _, _, sentence in chosen)
        if len(summary) > max_characters:
            summary = summary[:max_characters].rsplit(" ", 1)[0].rstrip() + "…"
        return summary
