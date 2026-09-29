from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from codemap.scanner import read_source_bytes


def normalized(vectors, *, dimension: int) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != dimension or not np.isfinite(matrix).all():
        raise ValueError("invalid embedding dimensions or non-finite vectors")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 0) or not np.isfinite(norms).all():
        raise ValueError("embeddings must be finite and non-zero")
    return matrix / norms


@dataclass(frozen=True)
class VectorMatch:
    chunk_id: str
    score: float


class VectorStore:
    def __init__(self, chunk_ids, embeddings, *, dimension):
        self.chunk_ids = tuple(chunk_ids)
        self.dimension = dimension
        if dimension < 1 or len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise ValueError("invalid vector index IDs or dimension")
        self.embeddings = normalized(embeddings, dimension=dimension)
        if len(self.chunk_ids) != len(self.embeddings):
            raise ValueError("vector count does not match chunk count")

    def save(self, path: Path, *, dir_fd=None):
        # Exclusive creation: snapshots are immutable and never overwrite source files.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "wb") as handle:
                np.save(handle, self.embeddings, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            os.unlink(path, dir_fd=dir_fd)
            raise

    @classmethod
    def load(cls, path: Path, chunk_ids, *, dimension):
        try:
            data = read_source_bytes(path, 512_000_000)
            matrix = np.load(io.BytesIO(data), allow_pickle=False)
            return cls(chunk_ids, matrix, dimension=dimension)
        except (OSError, ValueError, EOFError, TypeError) as exc:
            raise ValueError("invalid vector index; rebuild the index") from exc

    def search(self, query, *, limit=10, allowed_ids=None, min_score=0.0):
        if limit < 1 or not np.isfinite(min_score) or not -1 <= min_score <= 1:
            raise ValueError("invalid vector search options")
        query = normalized(np.asarray(query).reshape(1, -1), dimension=self.dimension)[0]
        scores = self.embeddings @ query
        candidates = [i for i, key in enumerate(self.chunk_ids)
                      if (allowed_ids is None or key in allowed_ids) and scores[i] >= min_score]
        candidates.sort(key=lambda i: (-float(scores[i]), self.chunk_ids[i]))
        return [VectorMatch(self.chunk_ids[i], float(scores[i])) for i in candidates[:limit]]
