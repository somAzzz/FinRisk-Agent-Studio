"""Pydantic AI integration boundary for incremental runtime migration."""

from src.ai.deps import (
    AgentDeps,
    AgentPermissions,
    AgentServices,
    AgentSubject,
)
from src.ai.model_factory import (
    AgentModelConfig,
    DeepSeekModelConfig,
    OpenAIModelConfig,
    SGLangModelConfig,
    VLLMModelConfig,
    build_agent_model,
    resolve_agent_model_config,
)

__all__ = [
    "AgentDeps",
    "AgentModelConfig",
    "AgentPermissions",
    "AgentServices",
    "AgentSubject",
    "DeepSeekModelConfig",
    "OpenAIModelConfig",
    "SGLangModelConfig",
    "VLLMModelConfig",
    "build_agent_model",
    "resolve_agent_model_config",
]
