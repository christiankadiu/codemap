from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class FileLoadError(Exception):
    pass


@dataclass(frozen=True)
class TextFile:
    path: Path
    content: str
    line_count: int
