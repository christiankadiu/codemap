from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from indexer import read_chunks


@dataclass(frozen=True)
class IndexStats:
    index_file: Path
    files: int
    chunks: int
    languages: dict[str, int]


def collect_stats(index_file: Path | str) -> IndexStats:
    path = Path(index_file).expanduser().resolve()
    chunks = read_chunks(path)
    files = {chunk.file for chunk in chunks}
    languages: Counter[str] = Counter(chunk.language for chunk in chunks)

    return IndexStats(
        index_file=path,
        files=len(files),
        chunks=len(chunks),
        languages=dict(sorted(languages.items())),
    )
