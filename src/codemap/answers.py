from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codemap.context import ContextSection, build_context, context_records, render_context
from codemap.privacy import redact


@dataclass(frozen=True)
class AnswerReference:
    file: str
    language: str
    start_line: int
    end_line: int
    score: float
    reference_id: str = ""


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
    max_chars: int = 12000,
    mode: str = "auto",
    embedding_provider=None,
    min_score: float = 0.2,
) -> AnswerRequest:
    clean_question = redact(question.strip())
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
            max_chars=max_chars,
            mode=mode,
            embedding_provider=embedding_provider,
            min_score=min_score,
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
                "reference_id": reference.reference_id,
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
            reference_id=f"S{index}",
        )
        for index, section in enumerate(sections, 1)
    )
