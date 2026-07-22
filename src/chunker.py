from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: str
    file: str
    language: str
    start_line: int
    end_line: int
    content: str
