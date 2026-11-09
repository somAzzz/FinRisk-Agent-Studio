"""Generation-policy boundary for Pydantic AI model runs."""

from __future__ import annotations

from pydantic_ai.settings import ModelSettings, merge_model_settings

from src.config import Settings, get_settings
from src.schemas.llm_config import AgentGenerationConfig


def build_model_settings(
    config: AgentGenerationConfig,
) -> ModelSettings | None:
    """Translate the project schema into Pydantic AI settings."""
    result: ModelSettings = {}

    if config.temperature is not None:
        result["temperature"] = config.temperature

    if config.max_tokens is not None:
        result["max_tokens"] = config.max_tokens

    if config.timeout_seconds is not None:
        result["timeout"] = config.timeout_seconds

    if config.thinking is not None:
        result["thinking"] = config.thinking

    return result or None


def application_generation_config(
    settings: Settings | None = None,
) -> AgentGenerationConfig:
    """Read application-wide generation defaults."""
    active = settings or get_settings()

    return AgentGenerationConfig(
        temperature=active.llm_temperature,
        max_tokens=active.llm_max_tokens,
        timeout_seconds=active.llm_timeout_seconds,
        thinking=active.llm_thinking,
    )


def resolve_model_settings(
    *,
    settings: Settings | None = None,
    agent_defaults: AgentGenerationConfig | None = None,
    run_override: AgentGenerationConfig | None = None,
) -> ModelSettings | None:
    """Resolve application < Agent < run generation precedence."""
    resolved = build_model_settings(application_generation_config(settings))

    if agent_defaults is not None:
        resolved = merge_model_settings(
            resolved,
            build_model_settings(agent_defaults),
        )

    if run_override is not None:
        resolved = merge_model_settings(
            resolved,
            build_model_settings(run_override),
        )

    return resolved


__all__ = [
    "application_generation_config",
    "build_model_settings",
    "resolve_model_settings",
]
