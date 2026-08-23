"""Central model/provider factory for Pydantic AI agents."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import Settings, get_settings
from src.schemas.llm_config import LLMProvider, LLMRunConfig


class _OpenAICompatibleConfig(BaseModel):
    """Validated connection contract for one OpenAI-compatible endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    model: str = Field(min_length=1)
    api_key: SecretStr
    timeout_s: float = Field(default=60.0, gt=0)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        return normalized


class SGLangModelConfig(_OpenAICompatibleConfig):
    provider: Literal["sglang"] = "sglang"


class VLLMModelConfig(_OpenAICompatibleConfig):
    provider: Literal["vllm"] = "vllm"


class DeepSeekModelConfig(_OpenAICompatibleConfig):
    provider: Literal["deepseek"] = "deepseek"


class OpenAIModelConfig(_OpenAICompatibleConfig):
    provider: Literal["openai"] = "openai"


AgentModelConfig = Annotated[
    SGLangModelConfig | VLLMModelConfig | DeepSeekModelConfig | OpenAIModelConfig,
    Field(discriminator="provider"),
]


def resolve_agent_model_config(
    run_config: LLMRunConfig | None = None,
    *,
    settings: Settings | None = None,
) -> AgentModelConfig:
    """Resolve per-run overrides against process settings without fallback drift."""
    active_settings = settings or get_settings()
    provider: LLMProvider
    if run_config is None:
        if active_settings.llm_provider not in {
            "sglang",
            "vllm",
            "deepseek",
            "openai",
        }:
            raise ValueError(
                f"Unsupported LLM_PROVIDER {active_settings.llm_provider!r}"
            )
        provider = active_settings.llm_provider  # type: ignore[assignment]
        base_url_override = None
        model_override = None
    else:
        provider = run_config.provider
        base_url_override = run_config.base_url
        model_override = run_config.model

    if provider == "sglang":
        return SGLangModelConfig(
            base_url=base_url_override or active_settings.sglang_base_url,
            model=model_override or active_settings.sglang_model,
            api_key=active_settings.sglang_api_key,
        )
    if provider == "vllm":
        return VLLMModelConfig(
            base_url=base_url_override or active_settings.vllm_base_url,
            model=model_override or active_settings.vllm_model,
            api_key=active_settings.vllm_api_key,
        )
    if provider == "deepseek":
        if not active_settings.deepseek_configured():
            raise ValueError(
                "DEEPSEEK_API_KEY is not configured with a non-placeholder value"
            )
        return DeepSeekModelConfig(
            base_url=base_url_override or active_settings.deepseek_base_url,
            model=model_override or active_settings.deepseek_model,
            api_key=active_settings.deepseek_api_key,
            timeout_s=active_settings.deepseek_timeout_s,
        )
    return OpenAIModelConfig(
        base_url=base_url_override or active_settings.openai_base_url,
        model=model_override or active_settings.openai_model,
        api_key=active_settings.openai_api_key,
    )


def _compatible_profile(config: AgentModelConfig) -> OpenAIModelProfile | None:
    """Describe conservative capabilities for non-OpenAI endpoints."""
    if config.provider == "openai":
        return None
    thinking_field = (
        "reasoning" if config.provider == "vllm" else "reasoning_content"
    )
    return OpenAIModelProfile(
        supports_json_schema_output=False,
        openai_supports_strict_tool_definition=False,
        openai_supports_tool_choice_required=False,
        openai_chat_thinking_field=thinking_field,
    )


def build_agent_model(config: AgentModelConfig) -> OpenAIChatModel:
    """Build a Pydantic AI model with an explicit endpoint and credentials."""
    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value(),
    )
    return OpenAIChatModel(
        config.model,
        provider=provider,
        profile=_compatible_profile(config),
    )


__all__ = [
    "AgentModelConfig",
    "DeepSeekModelConfig",
    "OpenAIModelConfig",
    "SGLangModelConfig",
    "VLLMModelConfig",
    "build_agent_model",
    "resolve_agent_model_config",
]
