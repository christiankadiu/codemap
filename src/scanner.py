from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from languages import EXTENSION_LANGUAGES, language_for_path


DEFAULT_EXTENSIONS = tuple(EXTENSION_LANGUAGES)

DEFAULT_IGNORED_DIRS = (
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "target",
    "venv",
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    language: str
    size_bytes: int


def _resolve_repository(root: Path | str) -> Path:
    path = Path(root).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {path}")

    return path


def _normalize_extensions(extensions: Iterable[str]) -> set[str]:
    return {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in extensions
    }


def _should_scan_directory(path: Path, ignored_dirs: Collection[str]) -> bool:
    return path.name not in ignored_dirs and not path.is_symlink()


def _source_file(root: Path, path: Path) -> SourceFile | None:
    try:
        size_bytes = path.stat().st_size
    except OSError:
        return None

    return SourceFile(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        language=language_for_path(path),
        size_bytes=size_bytes,
    )
