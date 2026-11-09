"""Central deployment-policy factory for Pydantic AI models."""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast
from urllib.parse import urlparse

from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import Settings, credential_configured, get_settings
from src.schemas.llm_config import LLMProvider, LLMRunConfig

OFFICIAL_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


class _CredentialedModelConfig(BaseModel):
    """Shared deployment fields that must never expose credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    api_key: SecretStr


class _OpenAICompatibleConfig(_CredentialedModelConfig):
    """Deployment contract for an OpenAI-compatible endpoint."""

    base_url: str

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


class OpenAIModelConfig(_OpenAICompatibleConfig):
    provider: Literal["openai"] = "openai"


class DeepSeekModelConfig(_CredentialedModelConfig):
    provider: Literal["deepseek"] = "deepseek"
    base_url: Literal["https://api.deepseek.com"] = OFFICIAL_DEEPSEEK_BASE_URL


AgentModelConfig = Annotated[
    SGLangModelConfig | VLLMModelConfig | DeepSeekModelConfig | OpenAIModelConfig,
    Field(discriminator="provider"),
]


def resolve_agent_model_config(
    run_config: LLMRunConfig | None = None,
    *,
    settings: Settings | None = None,
) -> AgentModelConfig:
    """Resolve deployment selection without mutating global state."""
    active = settings or get_settings()

    if run_config is None:
        provider_value = active.llm_provider
        base_url_override = None
        model_override = None
    else:
        provider_value = run_config.provider
        base_url_override = run_config.base_url
        model_override = run_config.model

    supported = {"sglang", "vllm", "deepseek", "openai"}
    if provider_value not in supported:
        raise ValueError(f"Unsupported LLM_PROVIDER {provider_value!r}")

    provider = cast(LLMProvider, provider_value)

    if provider in {"sglang", "vllm", "openai"}:
        endpoints = {
            "sglang": (active.sglang_base_url, active.sglang_model, active.sglang_api_key, SGLangModelConfig),
            "vllm": (active.vllm_base_url, active.vllm_model, active.vllm_api_key, VLLMModelConfig),
            "openai": (active.openai_base_url, active.openai_model, active.openai_api_key, OpenAIModelConfig),
        }
        endpoint, model, key, config_type = endpoints[provider]
        if provider == "openai" and not active.openai_configured():
            raise ValueError("OPENAI_API_KEY is not configured with a non-placeholder value")
        target = (base_url_override or endpoint).strip().rstrip("/")
        if target != endpoint.strip().rstrip("/"):
            if credential_configured(key):
                raise ValueError("A server credential can only be used with its configured endpoint")
            key = "EMPTY"
        return config_type(base_url=target, model=model_override or model, api_key=key)

    if base_url_override:
        normalized = base_url_override.strip().rstrip("/")
        if normalized != OFFICIAL_DEEPSEEK_BASE_URL:
            raise ValueError(
                f"Custom DeepSeek endpoints are not supported; expected {OFFICIAL_DEEPSEEK_BASE_URL!r}"
            )

    api_key = active.deepseek_api_key
    if not active.deepseek_configured() or api_key is None:
        raise ValueError("DEEPSEEK_API_KEY is not configured with a non-placeholder value")

    return DeepSeekModelConfig(
        model=model_override or active.deepseek_model,
        api_key=api_key,
    )


def _local_compatible_profile(
    config: SGLangModelConfig | VLLMModelConfig,
) -> OpenAIModelProfile:
    """Describe conservative local OpenAI-compatible capabilities."""
    thinking_field = "reasoning" if config.provider == "vllm" else "reasoning_content"

    return OpenAIModelProfile(
        supports_json_schema_output=True,
        openai_supports_strict_tool_definition=False,
        openai_supports_tool_choice_required=False,
        openai_chat_thinking_field=thinking_field,
    )


class SGLangChatModel(OpenAIChatModel):
    def _validate_completion(self, response: ChatCompletion):
        # SGLang emits weight history as a list; OpenAI metadata values are strings.
        metadata = response.metadata
        if metadata and isinstance(metadata.get("weight_versions"), list):
            normalized = {**metadata, "weight_versions": json.dumps(metadata["weight_versions"])}
            response = response.model_copy(update={"metadata": normalized})
        return super()._validate_completion(response)


def build_agent_model(
    config: AgentModelConfig,
) -> OpenAIChatModel:
    """Build a model from an already validated deployment config."""
    api_key = config.api_key.get_secret_value()

    if isinstance(config, DeepSeekModelConfig):
        return OpenAIChatModel(
            config.model,
            provider=DeepSeekProvider(api_key=api_key),
        )

    if isinstance(config, OpenAIModelConfig):
        provider = OpenAIProvider(
            base_url=config.base_url,
            api_key=api_key,
        )
        return OpenAIChatModel(
            config.model,
            provider=provider,
        )

    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=api_key,
    )
    model_class = SGLangChatModel if isinstance(config, SGLangModelConfig) else OpenAIChatModel
    return model_class(
        config.model,
        provider=provider,
        profile=_local_compatible_profile(config),
    )


__all__ = [
    "OFFICIAL_DEEPSEEK_BASE_URL",
    "OFFICIAL_OPENAI_BASE_URL",
    "AgentModelConfig",
    "DeepSeekModelConfig",
    "OpenAIModelConfig",
    "SGLangModelConfig",
    "VLLMModelConfig",
    "build_agent_model",
    "resolve_agent_model_config",
]
