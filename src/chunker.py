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


def _validate_chunk_options(max_lines: int, overlap_lines: int) -> None:
    if max_lines < 1:
        raise ValueError("max_lines must be greater than zero")
    if overlap_lines < 0:
        raise ValueError("overlap_lines must not be negative")
    if overlap_lines >= max_lines:
        raise ValueError("overlap_lines must be smaller than max_lines")
