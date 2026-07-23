from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from chunker import Chunk
from indexer import read_chunks
from scanner import scan_repository


@dataclass(frozen=True)
class IndexStatus:
    repository: Path
    index_file: Path
    indexed_files: int
    scanned_files: int
    unchanged_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    new_files: tuple[str, ...]

    @property
    def is_current(self) -> bool:
        return not self.changed_files and not self.missing_files and not self.new_files


def check_index(
    repository: Path | str,
    *,
    index_file: Path | str,
    max_file_size: int = 1_000_000,
) -> IndexStatus:
    root = Path(repository).expanduser().resolve()
    path = Path(index_file).expanduser().resolve()
    current_files = {
        source_file.relative_path: source_file.content_hash
        for source_file in scan_repository(root, max_file_size=max_file_size)
    }
    indexed_files = _indexed_file_hashes(read_chunks(path))
    shared_files = current_files.keys() & indexed_files.keys()

    unchanged_files = sorted(
        file
        for file in shared_files
        if current_files[file] == indexed_files[file]
    )
    changed_files = sorted(
        file
        for file in shared_files
        if current_files[file] != indexed_files[file]
    )
    missing_files = sorted(indexed_files.keys() - current_files.keys())
    new_files = sorted(current_files.keys() - indexed_files.keys())

    return IndexStatus(
        repository=root,
        index_file=path,
        indexed_files=len(indexed_files),
        scanned_files=len(current_files),
        unchanged_files=tuple(unchanged_files),
        changed_files=tuple(changed_files),
        missing_files=tuple(missing_files),
        new_files=tuple(new_files),
    )


def _indexed_file_hashes(chunks: Iterable[Chunk]) -> dict[str, str]:
    hashes_by_file: dict[str, set[str]] = {}

    for chunk in chunks:
        hashes_by_file.setdefault(chunk.file, set()).add(chunk.file_hash)

    return {
        file: _single_hash(hashes)
        for file, hashes in hashes_by_file.items()
    }


def _single_hash(hashes: set[str]) -> str:
    if len(hashes) != 1:
        return ""

    return next(iter(hashes))
