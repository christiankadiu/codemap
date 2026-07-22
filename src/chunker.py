from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: str
    file: str
    language: str
    start_line: int
    end_line: int
    content: str


def chunk_text(
    *,
    file: str,
    language: str,
    content: str,
    max_lines: int = 120,
    overlap_lines: int = 20,
) -> list[Chunk]:
    _validate_chunk_options(max_lines, overlap_lines)

    lines = content.splitlines()
    if not lines:
        return []

    ranges = (
        _markdown_ranges(lines, max_lines, overlap_lines)
        if language == "markdown"
        else _line_windows(1, len(lines), max_lines, overlap_lines)
    )

    chunks: list[Chunk] = []
    for start_line, end_line in ranges:
        chunk_content = "\n".join(lines[start_line - 1 : end_line])
        if not chunk_content.strip():
            continue
        chunks.append(
            Chunk(
                id=_chunk_id(file, start_line, end_line, chunk_content),
                file=file,
                language=language,
                start_line=start_line,
                end_line=end_line,
                content=chunk_content,
            )
        )

    return chunks


def _validate_chunk_options(max_lines: int, overlap_lines: int) -> None:
    if max_lines < 1:
        raise ValueError("max_lines must be greater than zero")
    if overlap_lines < 0:
        raise ValueError("overlap_lines must not be negative")
    if overlap_lines >= max_lines:
        raise ValueError("overlap_lines must be smaller than max_lines")


def _markdown_ranges(
    lines: list[str],
    max_lines: int,
    overlap_lines: int,
) -> list[tuple[int, int]]:
    headings = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if line.lstrip().startswith("#")
    ]

    if not headings:
        return _line_windows(1, len(lines), max_lines, overlap_lines)

    ranges: list[tuple[int, int]] = []
    if headings[0] > 1:
        ranges.extend(_line_windows(1, headings[0] - 1, max_lines, overlap_lines))

    for index, start_line in enumerate(headings):
        end_line = headings[index + 1] - 1 if index + 1 < len(headings) else len(lines)
        ranges.extend(_line_windows(start_line, end_line, max_lines, overlap_lines))

    return ranges


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


def _chunk_id(file: str, start_line: int, end_line: int, content: str) -> str:
    value = f"{file}\0{start_line}\0{end_line}\0{content}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]
