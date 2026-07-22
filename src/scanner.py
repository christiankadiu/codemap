from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from languages import EXTENSION_LANGUAGES


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
