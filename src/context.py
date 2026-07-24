from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from search import SearchResult, search_index


@dataclass(frozen=True)
class ContextLine:
    number: int
    text: str
    matched: bool


@dataclass(frozen=True)
class ContextSection:
    file: str
    language: str
    start_line: int
    end_line: int
    score: float
    lines: tuple[ContextLine, ...]


def build_context(
    query: str,
    index_file: Path | str,
    *,
    limit: int = 5,
    language: str | None = None,
    path: str | None = None,
    lines_before: int = 2,
    lines_after: int = 2,
    max_lines: int = 80,
) -> list[ContextSection]:
    results = search_index(
        query,
        index_file,
        limit=limit,
        language=language,
        path=path,
    )
    return context_from_results(
        results,
        lines_before=lines_before,
        lines_after=lines_after,
        max_lines=max_lines,
    )


def context_from_results(
    results: Iterable[SearchResult],
    *,
    lines_before: int = 2,
    lines_after: int = 2,
    max_lines: int = 80,
) -> list[ContextSection]:
    _validate_options(lines_before, lines_after, max_lines)

    sections: list[ContextSection] = []
    remaining_lines = max_lines

    for result in results:
        if remaining_lines <= 0:
            break

        context_lines = _context_lines(result, lines_before, lines_after)
        if not context_lines:
            continue

        selected_lines = tuple(context_lines[:remaining_lines])
        sections.append(
            ContextSection(
                file=result.chunk.file,
                language=result.chunk.language,
                start_line=selected_lines[0].number,
                end_line=selected_lines[-1].number,
                score=result.score,
                lines=selected_lines,
            )
        )
        remaining_lines -= len(selected_lines)

    return sections


def render_context(sections: Iterable[ContextSection], *, max_line_length: int = 160) -> str:
    output: list[str] = []

    for index, section in enumerate(sections, start=1):
        if output:
            output.append("")

        output.append(f"{index}. {section.file}:{section.start_line}-{section.end_line}")
        output.append(f"   language: {section.language}")
        output.append(f"   score: {section.score:g}")

        previous_line: int | None = None
        for line in section.lines:
            if previous_line is not None and line.number > previous_line + 1:
                output.append("     ...")

            marker = ">" if line.matched else " "
            output.append(f"   {marker} {line.number}: {_trim_line(line.text, max_line_length)}")
            previous_line = line.number

    return "\n".join(output)


def context_records(sections: Iterable[ContextSection]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []

    for section in sections:
        records.append(
            {
                "file": section.file,
                "language": section.language,
                "start_line": section.start_line,
                "end_line": section.end_line,
                "score": section.score,
                "lines": [
                    {
                        "number": line.number,
                        "text": line.text,
                        "matched": line.matched,
                    }
                    for line in section.lines
                ],
            }
        )

    return records


def _context_lines(
    result: SearchResult,
    lines_before: int,
    lines_after: int,
) -> list[ContextLine]:
    chunk = result.chunk
    lines = chunk.content.splitlines()
    matched_lines = set(result.matched_lines)
    ranges = _line_ranges(
        result.matched_lines or (chunk.start_line,),
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        lines_before=lines_before,
        lines_after=lines_after,
    )
    selected: list[ContextLine] = []

    for start_line, end_line in ranges:
        for line_number in range(start_line, end_line + 1):
            text = lines[line_number - chunk.start_line]
            selected.append(
                ContextLine(
                    number=line_number,
                    text=text.rstrip(),
                    matched=line_number in matched_lines,
                )
            )

    return selected


def _line_ranges(
    lines: Iterable[int],
    *,
    start_line: int,
    end_line: int,
    lines_before: int,
    lines_after: int,
) -> list[tuple[int, int]]:
    ranges = sorted(
        (
            max(start_line, line - lines_before),
            min(end_line, line + lines_after),
        )
        for line in lines
    )
    merged: list[tuple[int, int]] = []

    for current_start, current_end in ranges:
        if not merged or current_start > merged[-1][1] + 1:
            merged.append((current_start, current_end))
            continue

        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, current_end))

    return merged


def _validate_options(lines_before: int, lines_after: int, max_lines: int) -> None:
    if lines_before < 0:
        raise ValueError("lines_before must not be negative")
    if lines_after < 0:
        raise ValueError("lines_after must not be negative")
    if max_lines < 1:
        raise ValueError("max_lines must be greater than zero")


def _trim_line(text: str, max_length: int) -> str:
    if max_length < 1 or len(text) <= max_length:
        return text

    if max_length <= 3:
        return "." * max_length

    return f"{text[: max_length - 3]}..."
