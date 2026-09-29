from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from codemap.indexer import read_chunks, read_index_metadata


@dataclass(frozen=True)
class IndexStats:
    index_file: Path
    format_version: int | None
    files: int
    chunks: int
    languages: dict[str, int]


def collect_stats(index_file: Path | str) -> IndexStats:
    path = Path(index_file).expanduser().absolute()
    metadata = read_index_metadata(path)
    chunks = read_chunks(path, metadata=metadata)
    files = {chunk.file for chunk in chunks}
    languages: Counter[str] = Counter({chunk.file: chunk.language for chunk in chunks}.values())

    return IndexStats(
        index_file=path,
        format_version=metadata.format_version if metadata else None,
        files=len(files),
        chunks=len(chunks),
        languages=dict(sorted(languages.items())),
    )
