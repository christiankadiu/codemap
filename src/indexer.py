from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_INDEX_DIR = ".repo-index"
DEFAULT_CHUNK_FILE = "chunks.jsonl"


@dataclass(frozen=True)
class IndexSummary:
    repository: Path
    index_file: Path
    files_seen: int
    files_indexed: int
    files_skipped: int
    chunks_written: int
    languages: dict[str, int]


def default_index_file(repository: Path | str) -> Path:
    return Path(repository).expanduser().resolve() / DEFAULT_INDEX_DIR / DEFAULT_CHUNK_FILE
