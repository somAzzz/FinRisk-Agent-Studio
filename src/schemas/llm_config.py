"""Per-run LLM provider configuration.

The frontend sends this object with workflow requests so a run can
select a local or cloud OpenAI-compatible backend without mutating
process-wide environment variables.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

LLMProvider = Literal["sglang", "vllm", "deepseek", "openai"]


class LLMRunConfig(BaseModel):
    """LLM provider selection for one workflow run."""

    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider = "sglang"
    base_url: str | None = None
    model: str | None = None


__all__ = ["LLMProvider", "LLMRunConfig"]
