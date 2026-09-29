from __future__ import annotations

from dataclasses import dataclass

from codemap.answers import AnswerReference, AnswerRequest
from codemap.privacy import redact
from codemap.provider_input import build_provider_input
from codemap.providers import BasicResponseProvider, ProviderOptions, ResponseProvider


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
    options: ProviderOptions | None = None,
) -> ResponseResult:
    selected_provider = provider or BasicResponseProvider()
    selected_options = options or ProviderOptions()
    provider_input = build_provider_input(request)
    provider_text = selected_provider.build_text(provider_input, selected_options)

    return ResponseResult(
        question=redact(request.question),
        text=redact(provider_text.text),
        references=request.references if request.has_context else (),
    )


def response_record(result: ResponseResult) -> dict[str, object]:
    return {
        "question": result.question,
        "text": result.text,
        "references": [
            {
                "file": reference.file,
                "reference_id": reference.reference_id,
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
        output.append(f"- [{reference.reference_id}] {reference.file}:{reference.start_line}-{reference.end_line}")

    return "\n".join(output)
