from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from chunker import Chunk


WORD_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+")

COMMON_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "show",
    "the",
    "to",
    "where",
    "which",
    "with",
}


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float
    matched_terms: tuple[str, ...]


def search_chunks(
    query: str,
    chunks: Iterable[Chunk],
    *,
    limit: int = 10,
) -> list[SearchResult]:
    if limit < 1:
        raise ValueError("limit must be greater than zero")

    query_terms = _query_terms(query)
    if not query_terms:
        return []

    results = [
        result
        for chunk in chunks
        if (result := _score_chunk(chunk, query_terms)).score > 0
    ]

    return sorted(
        results,
        key=lambda result: (-result.score, result.chunk.file, result.chunk.start_line),
    )[:limit]


def _score_chunk(chunk: Chunk, query_terms: tuple[str, ...]) -> SearchResult:
    content = chunk.content.casefold()
    file = chunk.file.casefold()
    language = chunk.language.casefold()
    content_counts = Counter(_words(chunk.content))
    matched_terms: list[str] = []
    score = 0.0

    for term in query_terms:
        term_score = 0.0
        term_score += content_counts[term] * 2

        if term in content:
            term_score += 1
        if term in file:
            term_score += 3
        if term == language:
            term_score += 1

        if term_score:
            matched_terms.append(term)
            score += term_score

    if len(query_terms) > 1 and " ".join(query_terms) in content:
        score += 4

    return SearchResult(chunk=chunk, score=score, matched_terms=tuple(matched_terms))


def _query_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()

    for word in _words(query):
        if word in COMMON_WORDS or word in seen:
            continue
        terms.append(word)
        seen.add(word)

    return tuple(terms)


def _words(value: str) -> list[str]:
    return [match.group(0).casefold() for match in WORD_PATTERN.finditer(value)]
