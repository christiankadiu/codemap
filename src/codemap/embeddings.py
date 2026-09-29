from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from codemap.chunker import Chunk

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
EMBEDDING_TEXT_VERSION = 1


class EmbeddingProvider(Protocol):
    model_name: str
    revision: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def embedding_text(chunk: Chunk) -> str:
    return f"File: {chunk.file}\nLanguage: {chunk.language}\nSymbol: {chunk.symbol or '-'}\n\n{chunk.content}"


def embedding_key(chunk: Chunk) -> str:
    return hashlib.sha256(embedding_text(chunk).encode()).hexdigest()


def embedding_config(provider: EmbeddingProvider) -> dict:
    return {"model": provider.model_name, "revision": provider.revision,
            "dimension": provider.dimension, "normalization": "l2",
            "text_version": EMBEDDING_TEXT_VERSION}


class LocalEmbeddingProvider:
    """Pinned safetensors weights; offline unless downloads are explicitly requested."""

    def __init__(self, model_name=DEFAULT_MODEL, revision=DEFAULT_REVISION,
                 *, allow_download=False, batch_size=32):
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", model_name):
            raise ValueError("embedding model must be a public model ID, not a local path or URL")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("embedding revision must be a pinned 40-character commit hash")
        if (model_name, revision) != (DEFAULT_MODEL, DEFAULT_REVISION):
            raise ValueError("embedding model is not the supported pinned model; rebuild the index")
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        self.model_name, self.revision, self.batch_size = model_name, revision, batch_size
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("install codemap[embeddings] to use local semantic retrieval") from exc
        try:
            self._model = SentenceTransformer(
                model_name, revision=revision, device="cpu", trust_remote_code=False,
                local_files_only=not allow_download, token=False,
                model_kwargs={"use_safetensors": True},
            )
            self.dimension = int(self._model.get_sentence_embedding_dimension())
        except Exception as exc:
            raise RuntimeError(
                "embedding model could not be loaded; run index --download-model once "
                "with embeddings dependencies installed"
            ) from exc

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        # Pool token windows so large code chunks are not silently truncated.
        vectors = np.empty((len(texts), self.dimension), dtype=np.float32)
        for first in range(0, len(texts), self.batch_size):
            passages, owners = [], []
            for offset, text in enumerate(texts[first:first + self.batch_size]):
                ids = self._model.tokenizer.encode(text, add_special_tokens=False)
                width = max(16, self._model.max_seq_length - 16)
                windows = [ids[i:i + width] for i in range(0, len(ids), width)] or [[]]
                for window in windows:
                    passages.append(self._model.tokenizer.decode(window, skip_special_tokens=True))
                    owners.append(first + offset)
            encoded = self._model.encode_document(
                passages, batch_size=self.batch_size, show_progress_bar=False,
                convert_to_numpy=True, normalize_embeddings=True,
            )
            for owner in set(owners):
                vectors[owner] = encoded[np.asarray(owners) == owner].mean(axis=0)
        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        if len(self._model.tokenizer.encode(text)) > self._model.max_seq_length:
            raise ValueError("query is too long for the embedding model; shorten it")
        return self._model.encode_query(text, show_progress_bar=False, convert_to_numpy=True,
                                        normalize_embeddings=True)
