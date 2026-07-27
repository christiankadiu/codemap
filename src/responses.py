from __future__ import annotations

from dataclasses import dataclass

from answers import AnswerReference, AnswerRequest
from context import ContextLine, ContextSection


@dataclass(frozen=True)
class ResponseResult:
    question: str
    text: str
    references: tuple[AnswerReference, ...]

    @property
    def has_references(self) -> bool:
        return bool(self.references)


def build_response(request: AnswerRequest) -> ResponseResult:
    if not request.has_context:
        return ResponseResult(
            question=request.question,
            text="No matching code found in the current index.",
            references=(),
        )

    return ResponseResult(
        question=request.question,
        text=_response_text(request),
        references=request.references,
    )


def response_record(result: ResponseResult) -> dict[str, object]:
    return {
        "question": result.question,
        "text": result.text,
        "references": [
            {
                "file": reference.file,
                "language": reference.language,
                "start_line": reference.start_line,
                "end_line": reference.end_line,
                "score": reference.score,
            }
            for reference in result.references
        ],
    }


def render_response(result: ResponseResult) -> str:
    output = [result.text]

    if not result.has_references:
        return "\n".join(output)

    output.append("")
    output.append("References:")
    for reference in result.references:
        output.append(f"- {reference.file}:{reference.start_line}-{reference.end_line}")

    return "\n".join(output)


def _response_text(request: AnswerRequest) -> str:
    first_reference = request.references[0]
    matched_lines = _matched_lines(request.context)

    output = [
        f"Found matching code in {first_reference.file}:{first_reference.start_line}-{first_reference.end_line}."
    ]

    if len(request.references) > 1:
        output.append(f"{len(request.references)} references were selected from the index.")

    if matched_lines:
        output.append(f"Matched lines: {_format_lines(matched_lines)}.")

    return " ".join(output)


def _matched_lines(sections: tuple[ContextSection, ...]) -> tuple[ContextLine, ...]:
    lines: list[ContextLine] = []

    for section in sections:
        lines.extend(line for line in section.lines if line.matched)

    return tuple(lines)


def _format_lines(lines: tuple[ContextLine, ...], *, limit: int = 8) -> str:
    selected = ", ".join(str(line.number) for line in lines[:limit])
    remaining = len(lines) - limit

    if remaining <= 0:
        return selected

    return f"{selected}, and {remaining} more"
