from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chunker import Chunk, chunk_text
from loader import read_text_file
from scanner import SourceFile


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


def _chunks_for_file(
    source_file: SourceFile,
    *,
    max_file_size: int,
    max_lines: int,
    overlap_lines: int,
) -> list[Chunk]:
    text_file = read_text_file(source_file.path, max_bytes=max_file_size)
    return chunk_text(
        file=source_file.relative_path,
        language=source_file.language,
        content=text_file.content,
        max_lines=max_lines,
        overlap_lines=overlap_lines,
    )
