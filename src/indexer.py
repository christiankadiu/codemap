from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from chunker import Chunk, chunk_text
from loader import FileLoadError, read_text_file
from scanner import SourceFile, scan_repository


DEFAULT_INDEX_DIR = ".repo-index"
DEFAULT_CHUNK_FILE = "chunks.jsonl"
DEFAULT_METADATA_FILE = "metadata.json"
INDEX_FORMAT_VERSION = 2


@dataclass(frozen=True)
class IndexSummary:
    repository: Path
    index_file: Path
    metadata_file: Path
    format_version: int
    files_seen: int
    files_indexed: int
    files_skipped: int
    chunks_written: int
    languages: dict[str, int]


@dataclass(frozen=True)
class IndexMetadata:
    format_version: int
    created_at: str
    chunk_file: str
    files_seen: int
    files_indexed: int
    files_skipped: int
    chunks_written: int
    languages: dict[str, int]


def default_index_file(repository: Path | str) -> Path:
    return Path(repository).expanduser().resolve() / DEFAULT_INDEX_DIR / DEFAULT_CHUNK_FILE


def metadata_file_for(index_file: Path | str) -> Path:
    path = Path(index_file).expanduser().resolve()

    if path.name == DEFAULT_CHUNK_FILE:
        return path.with_name(DEFAULT_METADATA_FILE)

    return path.with_name(f"{path.name}.metadata.json")


def build_index(
    repository: Path | str,
    *,
    index_file: Path | str | None = None,
    max_file_size: int = 1_000_000,
    max_lines: int = 120,
    overlap_lines: int = 20,
) -> IndexSummary:
    root = Path(repository).expanduser().resolve()
    output_file = Path(index_file).expanduser().resolve() if index_file else default_index_file(root)
    metadata_file = metadata_file_for(output_file)
    source_files = scan_repository(root, max_file_size=max_file_size)
    chunks: list[Chunk] = []
    files_indexed = 0
    files_skipped = 0
    languages: Counter[str] = Counter()

    for source_file in source_files:
        try:
            file_chunks = _chunks_for_file(
                source_file,
                max_file_size=max_file_size,
                max_lines=max_lines,
                overlap_lines=overlap_lines,
            )
        except FileLoadError:
            files_skipped += 1
            continue

        if not file_chunks:
            files_skipped += 1
            continue

        files_indexed += 1
        languages[source_file.language] += 1
        chunks.extend(file_chunks)

    chunks_written = _write_chunks(output_file, chunks)
    metadata = IndexMetadata(
        format_version=INDEX_FORMAT_VERSION,
        created_at=_current_timestamp(),
        chunk_file=output_file.name,
        files_seen=len(source_files),
        files_indexed=files_indexed,
        files_skipped=files_skipped,
        chunks_written=chunks_written,
        languages=dict(sorted(languages.items())),
    )
    _write_metadata(metadata_file, metadata)

    return IndexSummary(
        repository=root,
        index_file=output_file,
        metadata_file=metadata_file,
        format_version=INDEX_FORMAT_VERSION,
        files_seen=len(source_files),
        files_indexed=files_indexed,
        files_skipped=files_skipped,
        chunks_written=chunks_written,
        languages=dict(sorted(languages.items())),
    )


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


def _write_metadata(metadata_file: Path, metadata: IndexMetadata) -> None:
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=metadata_file.parent,
            prefix=f".{metadata_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(asdict(metadata), handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        os.replace(temporary_path, metadata_file)
        temporary_path = None
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def read_index_metadata(index_file: Path | str) -> IndexMetadata | None:
    metadata_file = metadata_file_for(index_file)

    try:
        with metadata_file.open(encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError:
        return None

    return IndexMetadata(
        format_version=int(record["format_version"]),
        created_at=str(record["created_at"]),
        chunk_file=str(record["chunk_file"]),
        files_seen=int(record["files_seen"]),
        files_indexed=int(record["files_indexed"]),
        files_skipped=int(record["files_skipped"]),
        chunks_written=int(record["chunks_written"]),
        languages=dict(record["languages"]),
    )


def read_chunks(index_file: Path | str) -> list[Chunk]:
    chunks: list[Chunk] = []

    with Path(index_file).expanduser().open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            record.setdefault("file_hash", "")
            chunks.append(Chunk(**record))

    return chunks


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        file_hash=source_file.content_hash,
        content=text_file.content,
        max_lines=max_lines,
        overlap_lines=overlap_lines,
    )
