from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: str
    file: str
    language: str
    file_hash: str
    start_line: int
    end_line: int
    content: str
    symbol: str | None = None
    symbol_type: str | None = None
    parent_symbol: str | None = None


def chunk_text(
    *,
    file: str,
    language: str,
    file_hash: str,
    content: str,
    max_lines: int = 120,
    overlap_lines: int = 20,
    strategy: str = "auto",
) -> list[Chunk]:
    _validate_chunk_options(max_lines, overlap_lines)
    if strategy not in ("auto", "lines"):
        raise ValueError("chunk strategy must be auto or lines")

    lines = content.splitlines()
    if not lines:
        return []

    if language == "python" and strategy == "auto":
        try:
            segments = _python_segments(content, len(lines))
        except (SyntaxError, ValueError, RecursionError):
            segments = [(1, len(lines), None, None, None)]
        chunks = []
        for start, end, symbol, kind, parent in segments:
            for first, last in _line_windows(start, end, max_lines, overlap_lines):
                text = "\n".join(lines[first - 1:last])
                if text.strip():
                    chunks.append(Chunk(_chunk_id(file, first, last, text), file, language,
                                        file_hash, first, last, text, symbol, kind, parent))
        return chunks

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
                file_hash=file_hash,
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


def _python_segments(content: str, line_count: int) -> list[tuple]:
    """Partition top-level declarations and methods without dropping module code."""
    tree = ast.parse(content)
    segments = []

    def start(node):
        return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])

    def partition(nodes, first, last, parent=None):
        cursor = first
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            begin, end = start(node), node.end_lineno
            if cursor < begin:
                segments.append((cursor, begin - 1, parent, "class" if parent else None, None))
            name = f"{parent}.{node.name}" if parent else node.name
            if isinstance(node, ast.ClassDef):
                partition(node.body, begin, end, name)
            else:
                segments.append((begin, end, name, "method" if parent else "function", parent))
            cursor = end + 1
        if cursor <= last:
            segments.append((cursor, last, parent, "class" if parent else None, None))

    partition(tree.body, 1, line_count)
    return segments
