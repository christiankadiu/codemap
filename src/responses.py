from __future__ import annotations

from dataclasses import dataclass

from answers import AnswerReference, AnswerRequest
from providers import BasicResponseProvider, ResponseProvider


@dataclass(frozen=True)
class ResponseResult:
    question: str
    text: str
    references: tuple[AnswerReference, ...]

    @property
    def has_references(self) -> bool:
        return bool(self.references)


def build_response(
    request: AnswerRequest,
    *,
    provider: ResponseProvider | None = None,
) -> ResponseResult:
    selected_provider = provider or BasicResponseProvider()
    provider_text = selected_provider.build_text(request)

    return ResponseResult(
        question=request.question,
        text=provider_text.text,
        references=request.references if request.has_context else (),
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
