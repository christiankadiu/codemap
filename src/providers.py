from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from context import ContextLine, ContextSection
from provider_input import ProviderInput


PROVIDER_NAMES = ("basic",)


@dataclass(frozen=True)
class ProviderText:
    text: str


@dataclass(frozen=True)
class ProviderOptions:
    model: str | None = None
    timeout_seconds: float = 30.0


class ResponseProvider(Protocol):
    def build_text(
        self,
        provider_input: ProviderInput,
        options: ProviderOptions,
    ) -> ProviderText:
        ...


@dataclass(frozen=True)
class BasicResponseProvider:
    def build_text(
        self,
        provider_input: ProviderInput,
        options: ProviderOptions,
    ) -> ProviderText:
        if not provider_input.has_context:
            return ProviderText("No matching code found in the current index.")

        first_reference = provider_input.references[0]
        matched_lines = _matched_lines(provider_input.context)
        output = [
            f"Found matching code in {first_reference.file}:{first_reference.start_line}-{first_reference.end_line}."
        ]

        if len(provider_input.references) > 1:
            output.append(f"{len(provider_input.references)} references were selected from the index.")

        if matched_lines:
            output.append(f"Matched lines: {_format_lines(matched_lines)}.")

        return ProviderText(" ".join(output))


def provider_names() -> tuple[str, ...]:
    return PROVIDER_NAMES


def provider_for_name(name: str) -> ResponseProvider:
    provider_name = name.strip().casefold()

    if provider_name == "basic":
        return BasicResponseProvider()

    raise ValueError(f"unsupported provider: {name}")


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
