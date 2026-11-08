"""Provider contract tests for the Pydantic AI model factory."""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.providers.deepseek import DeepSeekProvider

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
        ("openai", OpenAIModelConfig, "https://api.openai.com/v1"),
    ],
)
def test_resolve_provider_matrix(provider: str, expected_type: type, expected_base_url: str) -> None:
    config = resolve_agent_model_config(
        LLMRunConfig(provider=provider),  # type: ignore[arg-type]
        settings=Settings(
            deepseek_api_key="test-key",
            openai_api_key="test-key",
        ),
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


def test_official_deepseek_uses_native_provider_profile() -> None:
    config = resolve_agent_model_config(
        LLMRunConfig(provider="deepseek"),
        settings=Settings(deepseek_api_key="test-key"),
    )

    model = build_agent_model(config)

    assert isinstance(model.provider, DeepSeekProvider)
    assert model.system == "deepseek"
    assert model.base_url == "https://api.deepseek.com"
    assert model.profile["openai_chat_thinking_field"] == "reasoning_content"


def test_custom_deepseek_endpoint_is_rejected_explicitly() -> None:
    with pytest.raises(
        ValueError,
        match="Custom DeepSeek endpoints are not supported",
    ):
        resolve_agent_model_config(
            LLMRunConfig(
                provider="deepseek",
                base_url="https://deepseek-proxy.example/v1",
            ),
            settings=Settings(deepseek_api_key="test-key"),
        )


@pytest.mark.parametrize(
    "api_key",
    [None, "", "EMPTY", "dummy", "REPLACE_ME", "replace-me-before-use"],
)
def test_openai_placeholder_credentials_fail_before_network(api_key) -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        resolve_agent_model_config(
            LLMRunConfig(provider="openai"),
            settings=Settings(openai_api_key=api_key),
        )


def test_secret_is_redacted_from_config_repr() -> None:
    config = OpenAIModelConfig(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="super-secret-key",
    )

    rendered = repr(config)

    assert "super-secret-key" not in rendered
    assert "**********" in rendered


def test_sglang_accepts_structured_weight_version_metadata() -> None:
    from openai.types.chat import ChatCompletion

    model = build_agent_model(SGLangModelConfig(
        model="qwen3.8-27b", base_url="http://localhost:30000/v1", api_key="dummy"
    ))
    response = ChatCompletion.model_validate({
        "id": "test", "created": 1, "model": model.model_name, "object": "chat.completion",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "READY"}}],
    }).model_copy(update={"metadata": {"weight_versions": [{"version": "default", "start": 0, "end": 2}]}})
    assert model._process_response(response).parts[0].content == "READY"


@pytest.mark.parametrize("provider", ["openai", "sglang", "vllm"])
def test_run_cannot_redirect_server_credentials(provider):
    settings = Settings(**{f"{provider}_api_key": "server-owned-test-secret"})
    with pytest.raises(ValueError, match="endpoint"):
        resolve_agent_model_config(
            LLMRunConfig(provider=provider, base_url="https://untrusted.invalid/v1"),
            settings=settings,
        )


def test_official_openai_endpoint_is_explicit(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid/v1")
    config = OpenAIModelConfig(base_url="https://api.openai.com/v1", api_key="test", model="test")
    assert build_agent_model(config).base_url.rstrip("/") == config.base_url
