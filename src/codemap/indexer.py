from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from codemap.chunker import Chunk, _validate_chunk_options, chunk_text
from codemap.embeddings import EmbeddingProvider, embedding_config, embedding_key, embedding_text
from codemap.languages import EXTENSION_LANGUAGES
from codemap.privacy import PRIVACY_VERSION, redact, safe_relative_path, sensitive_path
from codemap.scanner import open_directory, read_source_bytes, scan_repository
from codemap.vector_store import VectorStore

DEFAULT_INDEX_DIR = ".repo-index"
DEFAULT_CHUNK_FILE = "index.json"
INDEX_FORMAT_VERSION = 3
MAX_INDEX_BYTES = 512_000_000


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
    files_reused: int = 0
    embeddings_reused: int = 0
    embeddings_created: int = 0
    redacted_files: int = 0


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
    chunk_sha256: str
    file_hashes: dict[str, str]
    settings: dict
    embedding: dict | None = None
    vector_file: str | None = None
    vector_sha256: str | None = None
    redacted_files: tuple[str, ...] = field(default_factory=tuple)


def default_index_file(repository: Path | str) -> Path:
    return Path(repository).expanduser().absolute() / DEFAULT_INDEX_DIR / DEFAULT_CHUNK_FILE


def metadata_file_for(index_file: Path | str) -> Path:
    return Path(index_file).expanduser().absolute()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _private_safe_path(value: object) -> bool:
    return safe_relative_path(value) and not sensitive_path(value) and redact(value) == value


def _asset_path(index_file: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name.startswith("snapshot-")
            or not safe_relative_path(name) or Path(name).name != name):
        raise ValueError("unsafe index asset path; rebuild the index")
    path = index_file.parent / name
    if path.is_symlink():
        raise ValueError("index assets must not be symlinks")
    return path


def _read_asset(index_file: Path, name: str, checksum: str) -> bytes:
    data = read_source_bytes(_asset_path(index_file, name), MAX_INDEX_BYTES)
    if _digest(data) != checksum:
        raise ValueError("index checksum mismatch; rebuild the index")
    return data


def build_index(
    repository: Path | str, *, index_file: Path | str | None = None,
    max_file_size: int = 1_000_000, max_lines: int = 120, overlap_lines: int = 20,
    strategy: str = "auto", embedding_provider: EmbeddingProvider | None = None,
    incremental: bool = True, batch_size: int = 32,
) -> IndexSummary:
    _validate_chunk_options(max_lines, overlap_lines)
    if strategy not in ("auto", "lines") or batch_size < 1:
        raise ValueError("invalid indexing options")
    root = Path(repository).expanduser().resolve()
    output = Path(index_file).expanduser().absolute() if index_file else default_index_file(root)
    if output.suffix not in (".json", ".jsonl") or any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError("index must be a JSON path without symlinks")
    # Refuse to overwrite an unrelated file, even for a full rebuild.
    previous = read_index_metadata(output) if output.exists() else None
    settings = {"max_file_size": max_file_size, "max_lines": max_lines,
                "overlap_lines": overlap_lines, "strategy": strategy,
                "privacy_version": PRIVACY_VERSION, "chunker_version": 1}
    source_files = scan_repository(root, max_file_size=max_file_size)
    reusable = bool(incremental and previous and previous.settings == settings)
    old_chunks = read_chunks(output, metadata=previous) if reusable else []
    by_file: dict[str, list[Chunk]] = {}
    for chunk in old_chunks:
        by_file.setdefault(chunk.file, []).append(chunk)
    chunks, redacted_files = [], []
    file_hashes = {}
    files_reused = 0
    for source in source_files:
        file_hashes[source.relative_path] = source.content_hash
        if reusable and previous.file_hashes.get(source.relative_path) == source.content_hash:
            chunks.extend(by_file.get(source.relative_path, []))
            files_reused += 1
            if source.relative_path in previous.redacted_files:
                redacted_files.append(source.relative_path)
            continue
        raw = read_source_bytes(source.path, max_file_size)
        if _digest(raw) != source.content_hash:
            raise RuntimeError("repository changed during indexing; retry once edits are complete")
        if b"\x00" in raw:
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        clean = redact(text)
        if clean != text:
            redacted_files.append(source.relative_path)
        chunks.extend(chunk_text(file=source.relative_path, language=source.language,
                                 file_hash=source.content_hash, content=clean,
                                 max_lines=max_lines, overlap_lines=overlap_lines, strategy=strategy))

    config = embedding_config(embedding_provider) if embedding_provider else None
    cache = {}
    if embedding_provider and reusable and previous.embedding == config:
        old_vectors = load_vectors(output, old_chunks, previous)
        cache = {embedding_key(c): old_vectors.embeddings[i] for i, c in enumerate(old_chunks)}
    reused, created = 0, 0
    store = None
    if embedding_provider:
        vectors = np.empty((len(chunks), embedding_provider.dimension), dtype=np.float32)
        pending = []
        for i, chunk in enumerate(chunks):
            key = embedding_key(chunk)
            if key in cache:
                vectors[i] = cache[key]
                reused += 1
            else:
                pending.append(i)
        for start in range(0, len(pending), batch_size):
            positions = pending[start:start + batch_size]
            encoded = embedding_provider.embed_documents([embedding_text(chunks[i]) for i in positions])
            if np.asarray(encoded).shape != (len(positions), embedding_provider.dimension):
                raise ValueError("embedding provider returned an incorrect batch shape")
            vectors[positions] = encoded
            created += len(positions)
        store = VectorStore([c.id for c in chunks], vectors, dimension=embedding_provider.dimension)

    languages = Counter({c.file: c.language for c in chunks}.values())
    indexed_files = len({c.file for c in chunks})
    generation = f"snapshot-{uuid.uuid4().hex}"
    chunk_file = output.parent / f"{generation}.jsonl"
    vector_file = output.parent / f"{generation}.npy"
    chunk_bytes = "".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks).encode()
    # Keep all writes and cleanup relative to one pinned directory descriptor.
    with open_directory(output.parent, create=True) as directory:
        written: list[str] = []
        try:
            _write_exclusive(chunk_file.name, chunk_bytes, directory)
            written.append(chunk_file.name)
            vector_sha = None
            if store:
                buffer = io.BytesIO()
                np.save(buffer, store.embeddings, allow_pickle=False)
                vector_bytes = buffer.getvalue()
                if len(vector_bytes) > MAX_INDEX_BYTES:
                    raise ValueError("vector index exceeds size limit")
                _write_exclusive(vector_file.name, vector_bytes, directory)
                written.append(vector_file.name)
                vector_sha = _digest(vector_bytes)
            metadata = IndexMetadata(
                INDEX_FORMAT_VERSION, datetime.now(UTC).isoformat(timespec="seconds"),
                chunk_file.name, len(source_files), indexed_files, len(source_files) - indexed_files,
                len(chunks), dict(sorted(languages.items())), _digest(chunk_bytes), file_hashes, settings,
                config, vector_file.name if store else None, vector_sha, tuple(redacted_files),
            )
            _write_manifest(output, metadata, directory)
        except BaseException:
            for asset in written:
                os.unlink(asset, dir_fd=directory)
            raise
    return IndexSummary(root, output, output, INDEX_FORMAT_VERSION, len(source_files),
                        indexed_files, len(source_files) - indexed_files, len(chunks),
                        dict(sorted(languages.items())), files_reused, reused, created, len(redacted_files))


def _write_exclusive(path: str, data: bytes, directory: int):
    if len(data) > MAX_INDEX_BYTES:
        raise ValueError("index exceeds size limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(path, dir_fd=directory)
        raise


def _write_manifest(path: Path, metadata: IndexMetadata, directory: int):
    temporary = f".codemap-{uuid.uuid4().hex}"
    data = (json.dumps(asdict(metadata), ensure_ascii=False, indent=2) + "\n").encode()
    _write_exclusive(temporary, data, directory)
    try:
        # The only commit point. Existing readers retain their immutable snapshot.
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        os.unlink(temporary, dir_fd=directory)
        raise


def read_index_metadata(index_file: Path | str) -> IndexMetadata | None:
    path = Path(index_file).expanduser().absolute()
    try:
        data = read_source_bytes(path, MAX_INDEX_BYTES)
    except FileNotFoundError:
        return None
    try:
        record = json.loads(data)
        if record["format_version"] != INDEX_FORMAT_VERSION:
            raise ValueError("unsupported index format")
        metadata = IndexMetadata(**record)
        _asset_path(path, metadata.chunk_file)
        for key in ("files_seen", "files_indexed", "files_skipped", "chunks_written"):
            if type(getattr(metadata, key)) is not int or getattr(metadata, key) < 0:
                raise ValueError("invalid index counts")
        if not isinstance(metadata.settings, dict) or not isinstance(metadata.languages, dict):
            raise ValueError("invalid index settings")
        settings = metadata.settings
        if (type(settings.get("max_file_size")) is not int or settings["max_file_size"] < 1
                or type(settings.get("max_lines")) is not int
                or type(settings.get("overlap_lines")) is not int
                or settings.get("strategy") not in ("auto", "lines")
                or type(settings.get("privacy_version")) is not int
                or type(settings.get("chunker_version")) is not int):
            raise ValueError("invalid index settings")
        _validate_chunk_options(settings["max_lines"], settings["overlap_lines"])
        if not all(_private_safe_path(f) and _valid_hash(h)
                   for f, h in metadata.file_hashes.items()):
            raise ValueError("invalid file manifest")
        if (not _valid_hash(metadata.chunk_sha256)
                or metadata.files_seen != len(metadata.file_hashes)
                or metadata.files_indexed + metadata.files_skipped != metadata.files_seen
                or not all(k in EXTENSION_LANGUAGES.values() and type(v) is int and v > 0
                           for k, v in metadata.languages.items())
                or sum(metadata.languages.values()) != metadata.files_indexed
                or not isinstance(metadata.redacted_files, (list, tuple))
                or not all(isinstance(f, str) and f in metadata.file_hashes
                           for f in metadata.redacted_files)):
            raise ValueError("invalid index metadata")
        if metadata.embedding is not None:
            e = metadata.embedding
            if (not isinstance(e["model"], str) or not isinstance(e["revision"], str)
                    or type(e["dimension"]) is not int or e["dimension"] < 1
                    or e["normalization"] != "l2" or e["text_version"] != 1):
                raise ValueError("invalid embedding configuration")
            _asset_path(path, metadata.vector_file)
            if not _valid_hash(metadata.vector_sha256):
                raise ValueError("invalid vector checksum")
        elif metadata.vector_file is not None or metadata.vector_sha256 is not None:
            raise ValueError("unexpected vector asset")
        return metadata
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValueError("invalid or old index format; rebuild with codemap index") from exc


def read_chunks(index_file: Path | str, *, metadata: IndexMetadata | None = None) -> list[Chunk]:
    path = Path(index_file).expanduser().absolute()
    metadata = metadata or read_index_metadata(path)
    if metadata is None:
        raise ValueError("index not found; run codemap index first")
    try:
        data = _read_asset(path, metadata.chunk_file, metadata.chunk_sha256)
        chunks = [Chunk(**json.loads(line)) for line in data.splitlines() if line.strip()]
        if len(chunks) != metadata.chunks_written or len({c.id for c in chunks}) != len(chunks):
            raise ValueError("chunk count or IDs do not match the manifest")
        for c in chunks:
            if (not isinstance(c.id, str) or not re.fullmatch(r"[a-f0-9]{16}", c.id)
                    or not _private_safe_path(c.file)
                    or c.language not in EXTENSION_LANGUAGES.values()
                    or not _valid_hash(c.file_hash)
                    or metadata.file_hashes.get(c.file) != c.file_hash
                    or not all(value is None or (isinstance(value, str) and redact(value) == value
                                                  and "\n" not in value and "\r" not in value)
                               for value in (c.symbol, c.symbol_type, c.parent_symbol))
                    or type(c.start_line) is not int or type(c.end_line) is not int
                    or c.start_line < 1 or c.end_line < c.start_line
                    or not isinstance(c.content, str)
                    or len(c.content.split("\n")) != c.end_line - c.start_line + 1
                    or redact(c.content) != c.content):
                raise ValueError("invalid chunk")
        return chunks
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValueError("invalid chunk snapshot; rebuild the index") from exc


def load_vectors(index_file: Path, chunks: list[Chunk], metadata: IndexMetadata) -> VectorStore:
    if not metadata.embedding or not metadata.vector_file:
        raise ValueError("index has no embeddings; rebuild with --embeddings")
    # Decode the exact bytes whose checksum was verified, without reopening a path.
    data = _read_asset(index_file, metadata.vector_file, metadata.vector_sha256)
    try:
        matrix = np.load(io.BytesIO(data), allow_pickle=False)
        return VectorStore([c.id for c in chunks], matrix, dimension=metadata.embedding["dimension"])
    except (OSError, ValueError, EOFError, TypeError) as exc:
        raise ValueError("invalid vector index; rebuild the index") from exc
