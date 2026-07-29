from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from providers import ProviderOptions, provider_names


DEFAULT_PROVIDER = "basic"
DEFAULT_TIMEOUT_SECONDS = 30.0

ENV_PROVIDER = "CODEMAP_PROVIDER"
ENV_MODEL = "CODEMAP_MODEL"
ENV_TIMEOUT_SECONDS = "CODEMAP_TIMEOUT_SECONDS"


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str
    model: str | None
    timeout_seconds: float


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
    )


def config_record(config: RuntimeConfig) -> dict[str, object]:
    return {
        "provider": config.provider,
        "model": _model_status(config),
        "timeout_seconds": config.timeout_seconds,
    }


def render_config(config: RuntimeConfig) -> str:
    return "\n".join(
        (
            f"Provider: {config.provider}",
            f"Model: {_model_status(config)}",
            f"Timeout: {_format_timeout(config.timeout_seconds)}",
        )
    )


def provider_options(config: RuntimeConfig) -> ProviderOptions:
    return ProviderOptions(
        model=config.model,
        timeout_seconds=config.timeout_seconds,
    )


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

    if timeout <= 0:
        raise ValueError(f"{ENV_TIMEOUT_SECONDS} must be greater than zero")

    return timeout


def _model_status(config: RuntimeConfig) -> str:
    return "configured" if config.model else "none"


def _format_timeout(timeout_seconds: float) -> str:
    if timeout_seconds.is_integer():
        return str(int(timeout_seconds))

    return str(timeout_seconds)


def _optional_value(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()
    return text or None
