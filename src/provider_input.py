from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from answers import AnswerReference, AnswerRequest
from context import ContextSection, context_records, render_context


DEFAULT_RESPONSE_RULES = (
    "Answer only from the provided code context.",
    "If the context is insufficient, say that the indexed code does not contain enough information.",
    "Cite the file and line ranges used for the answer.",
    "Keep the answer concise and technical.",
)


@dataclass(frozen=True)
class ProviderInput:
    question: str
    rules: tuple[str, ...]
    references: tuple[AnswerReference, ...]
    context: tuple[ContextSection, ...]

    @property
    def has_context(self) -> bool:
        return bool(self.context)


def build_provider_input(
    request: AnswerRequest,
    *,
    rules: Iterable[str] = DEFAULT_RESPONSE_RULES,
) -> ProviderInput:
    clean_rules = tuple(rule.strip() for rule in rules if rule.strip())
    if not clean_rules:
        raise ValueError("rules must not be empty")

    return ProviderInput(
        question=request.question,
        rules=clean_rules,
        references=request.references,
        context=request.context,
    )


def provider_input_record(provider_input: ProviderInput) -> dict[str, object]:
    return {
        "question": provider_input.question,
        "rules": list(provider_input.rules),
        "references": [
            {
                "file": reference.file,
                "language": reference.language,
                "start_line": reference.start_line,
                "end_line": reference.end_line,
                "score": reference.score,
            }
            for reference in provider_input.references
        ],
        "context": context_records(provider_input.context),
    }


def render_provider_input(provider_input: ProviderInput) -> str:
    output = [
        "Question:",
        provider_input.question,
        "",
        "Rules:",
    ]
    output.extend(f"- {rule}" for rule in provider_input.rules)

    output.append("")
    output.append("References:")
    if provider_input.references:
        for reference in provider_input.references:
            output.append(
                f"- {reference.file}:{reference.start_line}-{reference.end_line}"
                f" ({reference.language}, score {reference.score:g})"
            )
    else:
        output.append("none")

    output.append("")
    output.append("Context:")
    if provider_input.has_context:
        output.append(render_context(provider_input.context))
    else:
        output.append("none")

    return "\n".join(output)
