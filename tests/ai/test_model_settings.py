"""Generation-policy tests for Pydantic AI runs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ai.model_settings import build_model_settings, resolve_model_settings
from src.config import Settings
from src.schemas.llm_config import AgentGenerationConfig


def test_empty_generation_config_preserves_provider_defaults() -> None:
    assert build_model_settings(AgentGenerationConfig()) is None


def test_zero_temperature_is_preserved() -> None:
    result = build_model_settings(AgentGenerationConfig(temperature=0))

    assert result == {"temperature": 0}


@pytest.mark.parametrize(
    "values",
    [
        {"max_tokens": 0},
        {"timeout_seconds": 0},
        {"temperature": 2.1},
        {"thinking": "turbo"},
    ],
)
def test_invalid_generation_values_fail_early(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentGenerationConfig.model_validate(values)


def test_resolution_precedence() -> None:
    result = resolve_model_settings(
        settings=Settings(
            llm_temperature=0.1,
            llm_max_tokens=2000,
            llm_timeout_seconds=60,
        ),
        agent_defaults=AgentGenerationConfig(
            temperature=0.2,
            max_tokens=1000,
        ),
        run_override=AgentGenerationConfig(
            temperature=0,
            thinking="high",
        ),
    )

    assert result == {
        "temperature": 0,
        "max_tokens": 1000,
        "timeout": 60,
        "thinking": "high",
    }
