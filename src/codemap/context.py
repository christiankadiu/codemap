from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from codemap.privacy import redact
from codemap.retriever import retrieve
from codemap.search import SearchResult


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
    max_chars: int = 12000,
    mode: str = "auto",
    embedding_provider=None,
    min_score: float = 0.2,
) -> list[ContextSection]:
    results = retrieve(
        query,
        index_file,
        limit=limit,
        language=language,
        path=path,
        mode=mode,
        provider=embedding_provider,
        min_score=min_score,
    )
    return context_from_results(
        results,
        lines_before=lines_before,
        lines_after=lines_after,
        max_lines=max_lines,
        max_chars=max_chars,
    )


def context_from_results(
    results: Iterable[SearchResult],
    *,
    lines_before: int = 2,
    lines_after: int = 2,
    max_lines: int = 80,
    max_chars: int = 12000,
) -> list[ContextSection]:
    _validate_options(lines_before, lines_after, max_lines)

    if max_chars < 1:
        raise ValueError("max_chars must be greater than zero")
    sections: list[ContextSection] = []
    remaining_lines = max_lines
    seen: set[tuple[str, int]] = set()
    remaining_chars = max_chars

    for result in results:
        if remaining_lines <= 0 or remaining_chars <= 0:
            break

        context_lines = _context_lines(result, lines_before, lines_after)
        if not context_lines:
            continue

        selected = []
        for line in context_lines:
            key = (result.chunk.file, line.number)
            if key in seen:
                continue
            if remaining_lines <= 0 or remaining_chars <= 0:
                break
            text = redact(line.text)[:max(0, remaining_chars - 1)]
            selected.append(ContextLine(line.number, text, line.matched))
            seen.add(key)
            remaining_lines -= 1
            remaining_chars -= len(text) + 1
        selected_lines = tuple(selected)
        if not selected_lines:
            continue
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
    # Merge by file and split gaps so every cited range consists of supplied lines.
    merged: dict[str, dict[int, ContextLine]] = {}
    info = {}
    for section in sections:
        merged.setdefault(section.file, {}).update({line.number: line for line in section.lines})
        info.setdefault(section.file, (section.language, section.score))
    output = []
    for file, numbered in merged.items():
        runs: list[list[ContextLine]] = []
        for number in sorted(numbered):
            if not runs or number != runs[-1][-1].number + 1:
                runs.append([])
            runs[-1].append(numbered[number])
        language, score = info[file]
        output.extend(ContextSection(file, language, run[0].number, run[-1].number,
                                     score, tuple(run)) for run in runs)
    return output


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
        # Redact complete blocks before serializing individual lines.
        clean_lines = redact("\n".join(line.text for line in section.lines)).split("\n") if section.lines else []
        records.append(
            {
                "file": redact(section.file),
                "language": redact(section.language),
                "start_line": section.start_line,
                "end_line": section.end_line,
                "score": section.score,
                "lines": [
                    {
                        "number": line.number,
                        "text": clean_text,
                        "matched": line.matched,
                    }
                    for line, clean_text in zip(section.lines, clean_lines, strict=True)
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
    # Clean the whole chunk before selecting excerpts, including partial keys.
    # Chunks use newline separators; preserve a final empty source line.
    lines = redact(chunk.content).split("\n")
    matched_lines = set(result.matched_lines)
    if not matched_lines:
        return [ContextLine(chunk.start_line + i, line, False) for i, line in enumerate(lines)]
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
