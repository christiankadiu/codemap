from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexStats:
    index_file: Path
    files: int
    chunks: int
    languages: dict[str, int]
