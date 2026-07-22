from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
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


def _write_chunks(index_file: Path, chunks: list[Chunk]) -> int:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=index_file.parent,
            prefix=f".{index_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)

            for chunk in chunks:
                json.dump(asdict(chunk), handle, ensure_ascii=False)
                handle.write("\n")

        os.replace(temporary_path, index_file)
        temporary_path = None
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    return len(chunks)


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
