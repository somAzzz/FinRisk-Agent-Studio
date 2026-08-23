"""Provider contract tests for the Pydantic AI model factory."""

from __future__ import annotations

import pytest
from pydantic_ai import models

from src.ai.model_factory import (
    DeepSeekModelConfig,
    OpenAIModelConfig,
    SGLangModelConfig,
    VLLMModelConfig,
    build_agent_model,
    resolve_agent_model_config,
)
from src.config import Settings
from src.schemas.llm_config import LLMRunConfig


@pytest.mark.parametrize(
    ("provider", "expected_type", "expected_base_url"),
    [
        ("sglang", SGLangModelConfig, "http://localhost:30000/v1"),
        ("vllm", VLLMModelConfig, "http://localhost:8000/v1"),
        ("deepseek", DeepSeekModelConfig, "https://api.deepseek.com"),
        ("openai", OpenAIModelConfig, "http://localhost:30000/v1"),
    ],
)
def test_resolve_provider_matrix(
    provider: str, expected_type: type, expected_base_url: str
) -> None:
    config = resolve_agent_model_config(
        LLMRunConfig(provider=provider),  # type: ignore[arg-type]
        settings=Settings(deepseek_api_key="test-key"),
    )

    assert isinstance(config, expected_type)
    assert config.base_url == expected_base_url


def test_per_run_endpoint_and_model_override_never_fall_back() -> None:
    config = resolve_agent_model_config(
        LLMRunConfig(
            provider="vllm",
            base_url="http://inference.internal:9000/v1/",
            model="local-risk-model",
        ),
        settings=Settings(),
    )
    model = build_agent_model(config)

    assert config.base_url == "http://inference.internal:9000/v1"
    assert model.base_url == "http://inference.internal:9000/v1/"
    assert model.model_name == "local-risk-model"
    assert "api.openai.com" not in model.base_url


@pytest.mark.parametrize("base_url", ["", "localhost:8000/v1", "ftp://host/v1"])
def test_invalid_endpoint_is_rejected(base_url: str) -> None:
    with pytest.raises(ValueError, match="base_url"):
        VLLMModelConfig(
            base_url=base_url,
            model="test-model",
            api_key="dummy",
        )


def test_real_model_requests_are_disabled_in_tests() -> None:
    assert models.ALLOW_MODEL_REQUESTS is False
    with pytest.raises(RuntimeError, match="Model requests are not allowed"):
        models.check_allow_model_requests()


@pytest.mark.parametrize(
    "api_key",
    [None, "", "EMPTY", "dummy", "REPLACE_ME", "replace-me-before-use"],
)
def test_deepseek_placeholder_credentials_fail_before_network(api_key) -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        resolve_agent_model_config(
            LLMRunConfig(provider="deepseek"),
            settings=Settings(deepseek_api_key=api_key),
        )
