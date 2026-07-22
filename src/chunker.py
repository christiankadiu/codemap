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


def _line_windows(
    start_line: int,
    end_line: int,
    max_lines: int,
    overlap_lines: int,
) -> list[tuple[int, int]]:
    if start_line > end_line:
        return []

    windows: list[tuple[int, int]] = []
    current_start = start_line

    while current_start <= end_line:
        current_end = min(end_line, current_start + max_lines - 1)
        windows.append((current_start, current_end))
        if current_end == end_line:
            break
        current_start = current_end - overlap_lines + 1

    return windows
