from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Collection, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from codemap.languages import EXTENSION_LANGUAGES, language_for_path
from codemap.privacy import redact, safe_relative_path, sensitive_path

DEFAULT_EXTENSIONS = tuple(EXTENSION_LANGUAGES)
DEFAULT_IGNORED_DIRS = (
    ".git", ".hg", ".svn", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "__pycache__", "build", "dist", "env", "node_modules", "target", "venv",
    ".repo-index", ".codex", ".agents", ".ssh", ".aws", ".azure", ".config",
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    language: str
    size_bytes: int
    content_hash: str


@contextmanager
def open_directory(path: Path, *, create: bool = False):
    """Pin each ancestor without following symlinks, even during directory swaps."""
    path = path.absolute()
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        yield directory
    finally:
        os.close(directory)


def read_source_bytes(path: Path, max_bytes: int) -> bytes:
    """Bound reads and refuse symlinks and special files (including named pipes)."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with open_directory(path.parent) as directory:
        fd = os.open(path.name, flags, dir_fd=directory)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("source is not a regular file within the size limit")
        data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("source exceeds size limit")
        return data


def scan_repository(
    root: Path | str, *, extensions: Iterable[str] | None = None,
    ignored_dirs: Collection[str] | None = None, max_file_size: int = 1_000_000,
) -> list[SourceFile]:
    if max_file_size < 1:
        raise ValueError("max_file_size must be greater than zero")
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError("repository must be an existing directory")
    extensions = DEFAULT_EXTENSIONS if extensions is None else extensions
    allowed = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    ignored = set(DEFAULT_IGNORED_DIRS) | set(ignored_dirs or ())
    rules_by_dir: dict[Path, list[tuple[Path, GitIgnoreSpec]]] = {}
    files: list[SourceFile] = []
    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        current = Path(dirpath)
        rules = list(rules_by_dir.get(current.parent, []))
        for name in (".gitignore", ".codemapignore"):
            ignore_file = current / name
            if ignore_file.exists() or ignore_file.is_symlink():
                try:
                    patterns = read_source_bytes(ignore_file, 1_000_000).decode("utf-8")
                    rules.append((current, GitIgnoreSpec.from_lines(patterns.splitlines())))
                except (OSError, ValueError) as exc:
                    raise ValueError("cannot safely read repository ignore rules") from exc
        rules_by_dir[current] = rules
        dirnames[:] = [name for name in sorted(dirnames)
                       if name not in ignored and not (current / name).is_symlink()
                       and not sensitive_path(name)
                       and not _is_ignored(current / name, rules, directory=True)]
        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(root_path).as_posix()
            if (path.suffix.lower() not in allowed or not safe_relative_path(relative)
                    or sensitive_path(relative) or redact(relative) != relative
                    or _is_ignored(path, rules)):
                continue
            try:
                data = read_source_bytes(path, max_file_size)
            except (OSError, ValueError):
                continue
            files.append(SourceFile(path, relative, language_for_path(path), len(data),
                                    hashlib.sha256(data).hexdigest()))
    return files


def _is_ignored(path: Path, rules: list[tuple[Path, GitIgnoreSpec]], *, directory=False) -> bool:
    ignored = False
    for base, spec in rules:
        relative = path.relative_to(base).as_posix() + ("/" if directory else "")
        decision = spec.check_file(relative).include
        if decision is not None:
            ignored = decision
    return ignored
