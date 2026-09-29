from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from codemap.providers import ProviderOptions, provider_names

DEFAULT_PROVIDER = "basic"
DEFAULT_TIMEOUT_SECONDS = 30.0

ENV_PROVIDER = "CODEMAP_PROVIDER"
ENV_MODEL = "CODEMAP_MODEL"
ENV_TIMEOUT_SECONDS = "CODEMAP_TIMEOUT_SECONDS"
ENV_REMOTE_ENDPOINT = "CODEMAP_REMOTE_ENDPOINT"
ENV_REMOTE_KEY = "CODEMAP_REMOTE_KEY"
ENV_CHAT_FORMAT = "CODEMAP_CHAT_FORMAT"
ENV_REASONING_EFFORT = "CODEMAP_REASONING_EFFORT"


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str
    model: str | None = field(repr=False)
    timeout_seconds: float
    remote_endpoint: str | None = field(repr=False)
    remote_access_key: str | None = field(repr=False)
    chat_format: str = "text"
    reasoning_effort: str | None = None


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    provider: str | None = None,
) -> RuntimeConfig:
    values = os.environ if env is None else env
    provider_value = _provider_value(provider if provider is not None else values.get(ENV_PROVIDER))

    return RuntimeConfig(
        provider=provider_value,
        model=_optional_value(values.get(ENV_MODEL)),
        timeout_seconds=_timeout_value(values.get(ENV_TIMEOUT_SECONDS)),
        remote_endpoint=_optional_value(values.get(ENV_REMOTE_ENDPOINT)),
        remote_access_key=_optional_value(values.get(ENV_REMOTE_KEY)),
        chat_format=_choice(values.get(ENV_CHAT_FORMAT), ("text", "json_schema"), ENV_CHAT_FORMAT) or "text",
        reasoning_effort=_choice(values.get(ENV_REASONING_EFFORT), ("low", "medium", "high"), ENV_REASONING_EFFORT),
    )


def config_record(config: RuntimeConfig) -> dict[str, object]:
    return {
        "provider": config.provider,
        "model": _model_status(config),
        "timeout_seconds": config.timeout_seconds,
        "remote_endpoint": _configured_status(config.remote_endpoint),
        "remote_auth": _configured_status(config.remote_access_key),
        "chat_format": config.chat_format,
        "reasoning_effort": config.reasoning_effort,
    }


def render_config(config: RuntimeConfig) -> str:
    return "\n".join(
        (
            f"Provider: {config.provider}",
            f"Model: {_model_status(config)}",
            f"Timeout: {_format_timeout(config.timeout_seconds)}",
            f"Remote endpoint: {_configured_status(config.remote_endpoint)}",
            f"Remote auth: {_configured_status(config.remote_access_key)}",
            f"Chat format: {config.chat_format}",
            f"Reasoning effort: {config.reasoning_effort or 'provider default'}",
        )
    )


def provider_options(config: RuntimeConfig, *, allow_remote: bool = False) -> ProviderOptions:
    return ProviderOptions(
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        remote_endpoint=config.remote_endpoint,
        remote_access_key=config.remote_access_key,
        allow_remote=allow_remote,
        chat_format=config.chat_format,
        reasoning_effort=config.reasoning_effort,
    )


def _choice(value: str | None, allowed: tuple[str, ...], name: str) -> str | None:
    clean = _optional_value(value)
    if clean is not None and clean not in allowed:
        raise ValueError(f"invalid choice for {name}")
    return clean


def _provider_value(value: str | None) -> str:
    provider = (_optional_value(value) or DEFAULT_PROVIDER).casefold()

    if provider not in provider_names():
        raise ValueError(f"unsupported provider in {ENV_PROVIDER}")

    return provider


def _timeout_value(value: str | None) -> float:
    text = _optional_value(value)
    if text is None:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        timeout = float(text)
    except ValueError as exc:
        raise ValueError(f"{ENV_TIMEOUT_SECONDS} must be a number") from exc

    if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
        raise ValueError(f"{ENV_TIMEOUT_SECONDS} must be finite and between 0 and 300 seconds")

    return timeout


def _model_status(config: RuntimeConfig) -> str:
    return "configured" if config.model else "none"


def _configured_status(value: str | None) -> str:
    return "configured" if value else "none"


def _format_timeout(timeout_seconds: float) -> str:
    if timeout_seconds.is_integer():
        return str(int(timeout_seconds))

    return str(timeout_seconds)


def _optional_value(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()
    return text or None
