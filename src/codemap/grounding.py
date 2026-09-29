"""Validate answer structure without treating valid citations as proof of accuracy."""

import json
import re

from codemap.provider_input import ProviderInput


class AnswerValidationError(RuntimeError):
    """A generated answer failed local validation; its raw content is not exposed."""


def answer_format(provider_input: ProviderInput) -> dict:
    return {"type": "json_schema", "json_schema": {
        "name": "grounded_answer", "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["text", "reference_ids"],
                "properties": {
                    "text": {"type": "string"},
                    "reference_ids": {"type": "array", "items": {
                        "type": "string",
                        "enum": [ref.reference_id for ref in provider_input.references],
                    }},
                },
            }}},
        },
    }}


def render_grounded_answer(content: object, provider_input: ProviderInput) -> str:
    allowed = {ref.reference_id for ref in provider_input.references}
    try:
        record = json.loads(content) if isinstance(content, str) else None
        if not isinstance(record, dict) or set(record) != {"claims"}:
            raise ValueError
        claims = record["claims"]
        if not isinstance(claims, list) or not 1 <= len(claims) <= 32:
            raise ValueError
        lines = []
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"text", "reference_ids"}:
                raise ValueError
            text, refs = claim["text"], claim["reference_ids"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            if not isinstance(refs, list) or not refs:
                raise ValueError
            if any(not isinstance(ref, str) or ref not in allowed for ref in refs):
                raise ValueError
            selected = [ref for ref in provider_input.references if ref.reference_id in refs]
            evidence = "\n".join(
                line.text for section in provider_input.context for line in section.lines
                if any(ref.file == section.file and ref.start_line <= line.number <= ref.end_line
                       for ref in selected)
            )
            # Targeted check for currency symbols attached to amounts, not a factuality proof.
            symbols = re.findall(r"([$€£¥₹])\s*\d|\d\s*([$€£¥₹])", text)
            if any((before or after) not in evidence for before, after in symbols):
                raise AnswerValidationError("remote answer introduced a currency symbol absent from its cited code")
            citations = " ".join(f"[{ref}]" for ref in dict.fromkeys(refs))
            lines.append(f"{text.strip()} {citations}")
        return "\n\n".join(lines)
    except (ValueError, TypeError, RecursionError):
        raise AnswerValidationError("remote answer has an invalid structure or missing/unknown reference IDs") from None
