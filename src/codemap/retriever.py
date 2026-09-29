from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

from codemap.embeddings import EmbeddingProvider, LocalEmbeddingProvider, embedding_config
from codemap.indexer import load_vectors, read_chunks, read_index_metadata
from codemap.privacy import redact
from codemap.search import SearchResult, search_chunks

MODES = ("auto", "lexical", "semantic", "hybrid")


def reciprocal_rank_fusion(*rankings, limit=10, k=60):
    if limit < 1 or k < 1:
        raise ValueError("fusion limit and k must be positive")
    scores, results = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, result in enumerate(ranking, 1):
            key = result.chunk.id
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
            # Semantic candidates retain full code blocks instead of lexical excerpts.
            results[key] = result
    keys = sorted(scores, key=lambda key: (-scores[key], results[key].chunk.file,
                                          results[key].chunk.start_line))
    return [replace(results[key], score=scores[key]) for key in keys[:limit]]


class Retriever:
    def __init__(self, index_file: Path | str, *, mode="auto", provider: EmbeddingProvider | None = None):
        if mode not in MODES:
            raise ValueError("unsupported retrieval mode")
        path = Path(index_file).expanduser().absolute()
        metadata = read_index_metadata(path)
        if metadata is None:
            raise ValueError("index not found; run codemap index first")
        self.mode = ("hybrid" if metadata.embedding else "lexical") if mode == "auto" else mode
        self.chunks = read_chunks(path, metadata=metadata)
        self.provider, self.vectors = None, None
        if self.mode != "lexical":
            self.vectors = load_vectors(path, self.chunks, metadata)
            self.provider = provider or LocalEmbeddingProvider(metadata.embedding["model"],
                                                               metadata.embedding["revision"])
            if embedding_config(self.provider) != metadata.embedding:
                raise ValueError("query embedding model does not match the index; rebuild the index")

    def search(self, query, *, limit=10, language=None, path=None, min_score=0.2):
        query = redact(query.strip())
        if limit < 1 or limit > 1000 or not math.isfinite(min_score) or not -1 <= min_score <= 1:
            raise ValueError("limit must be 1..1000 and min_score must be -1..1")
        if not query:
            return []
        if len(query) > 4000:
            raise ValueError("query must not exceed 4000 characters")
        candidates = [c for c in self.chunks
                      if (not language or c.language.casefold() == language.casefold())
                      and (not path or path.casefold() in c.file.casefold())]
        candidate_limit = min(1000, max(40, limit * 4))
        lexical = search_chunks(query, candidates, limit=candidate_limit)
        if self.mode == "lexical":
            return lexical[:limit]
        matches = self.vectors.search(self.provider.embed_query(query), limit=candidate_limit,
                                      allowed_ids={c.id for c in candidates}, min_score=min_score)
        by_id = {c.id: c for c in candidates}
        semantic = [SearchResult(by_id[m.chunk_id], m.score, (), ()) for m in matches]
        if self.mode == "semantic":
            return semantic[:limit]
        return reciprocal_rank_fusion(lexical, semantic, limit=limit)


def retrieve(query, index_file, *, mode="auto", provider=None, **options):
    return Retriever(index_file, mode=mode, provider=provider).search(query, **options)
