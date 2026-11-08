"""Per-run LLM deployment and generation configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.settings import ThinkingLevel

LLMProvider = Literal["sglang", "vllm", "deepseek", "openai"]


class LLMRunConfig(BaseModel):
    """Select where and which model should serve one workflow run."""

    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider = "sglang"
    base_url: str | None = None
    model: str | None = None


class AgentGenerationConfig(BaseModel):
    """Describe how a model should generate for one Agent run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    thinking: ThinkingLevel | None = None


__all__ = [
    "AgentGenerationConfig",
    "LLMProvider",
    "LLMRunConfig",
]
