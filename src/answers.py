from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context import ContextSection, build_context, context_records, render_context


@dataclass(frozen=True)
class AnswerReference:
    file: str
    language: str
    start_line: int
    end_line: int
    score: float


@dataclass(frozen=True)
class AnswerRequest:
    question: str
    context: tuple[ContextSection, ...]
    references: tuple[AnswerReference, ...]

    @property
    def has_context(self) -> bool:
        return bool(self.context)


def build_answer_request(
    question: str,
    index_file: Path | str,
    *,
    limit: int = 5,
    language: str | None = None,
    path: str | None = None,
    lines_before: int = 2,
    lines_after: int = 2,
    max_lines: int = 80,
) -> AnswerRequest:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question must not be empty")

    sections = tuple(
        build_context(
            clean_question,
            index_file,
            limit=limit,
            language=language,
            path=path,
            lines_before=lines_before,
            lines_after=lines_after,
            max_lines=max_lines,
        )
    )

    return AnswerRequest(
        question=clean_question,
        context=sections,
        references=_references_for(sections),
    )


def answer_request_record(request: AnswerRequest) -> dict[str, object]:
    return {
        "question": request.question,
        "references": [
            {
                "file": reference.file,
                "language": reference.language,
                "start_line": reference.start_line,
                "end_line": reference.end_line,
                "score": reference.score,
            }
            for reference in request.references
        ],
        "context": context_records(request.context),
    }


def render_answer_request(request: AnswerRequest) -> str:
    output = [f"Question: {request.question}"]

    if not request.has_context:
        output.append("")
        output.append("No context")
        return "\n".join(output)

    output.append("")
    output.append("References:")
    for reference in request.references:
        output.append(
            f"- {reference.file}:{reference.start_line}-{reference.end_line}"
            f" ({reference.language}, score {reference.score:g})"
        )

    output.append("")
    output.append("Context:")
    output.append(render_context(request.context))
    return "\n".join(output)


def _references_for(sections: tuple[ContextSection, ...]) -> tuple[AnswerReference, ...]:
    return tuple(
        AnswerReference(
            file=section.file,
            language=section.language,
            start_line=section.start_line,
            end_line=section.end_line,
            score=section.score,
        )
        for section in sections
    )
