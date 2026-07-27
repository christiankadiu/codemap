from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from answers import AnswerRequest
from context import ContextLine, ContextSection


@dataclass(frozen=True)
class ProviderText:
    text: str


class ResponseProvider(Protocol):
    def build_text(self, request: AnswerRequest) -> ProviderText:
        ...


@dataclass(frozen=True)
class BasicResponseProvider:
    def build_text(self, request: AnswerRequest) -> ProviderText:
        if not request.has_context:
            return ProviderText("No matching code found in the current index.")

        first_reference = request.references[0]
        matched_lines = _matched_lines(request.context)
        output = [
            f"Found matching code in {first_reference.file}:{first_reference.start_line}-{first_reference.end_line}."
        ]

        if len(request.references) > 1:
            output.append(f"{len(request.references)} references were selected from the index.")

        if matched_lines:
            output.append(f"Matched lines: {_format_lines(matched_lines)}.")

        return ProviderText(" ".join(output))


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
