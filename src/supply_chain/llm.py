"""Typed Pydantic AI boundary for real supply-chain investigation steps."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from src.ai.deps import AgentServices
from src.ai.model_factory import build_agent_model, resolve_agent_model_config
from src.ai.store_factory import get_agent_run_recorder
from src.ai.structured_clients import PydanticAISupplyChainClient
from src.config import get_settings
from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.llm_models import (
    NodeProfileBatch,
    RequirementDecomposition,
    SupplierProposalBatch,
)
from src.supply_chain.models import ProviderCall


class SupplyChainAnalysisClient(Protocol):
    """Dedicated operations required by the supply-chain workflow."""

    provider: str

    def decompose_requirements(self, prompt: str) -> RequirementDecomposition: ...

    def propose_suppliers(self, prompt: str) -> SupplierProposalBatch: ...

    def profile_nodes(self, prompt: str) -> NodeProfileBatch: ...


def build_supply_chain_llm_client(
    config: LLMRunConfig | None,
) -> PydanticAISupplyChainClient | None:
    """Build the single typed client used by supply-chain model operations."""
    resolved = config or LLMRunConfig()
    try:
        settings = get_settings()
        return PydanticAISupplyChainClient(
            model=build_agent_model(
                resolve_agent_model_config(resolved, settings=settings)
            ),
            settings=settings,
            services=AgentServices(message_recorder=get_agent_run_recorder()),
        )
    except Exception:
        return None


def call_with_trace[OutputT](
    *,
    provider: str,
    operation: str,
    call: Callable[[], OutputT],
    retries: int = 1,
) -> tuple[OutputT | None, ProviderCall]:
    """Execute one typed model operation and capture its provider trace."""
    started = time.perf_counter()
    last_error: Exception | None = None
    for _attempt in range(max(1, retries + 1)):
        try:
            output = call()
            return output, ProviderCall(
                provider=provider,
                operation=operation,
                status="success",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            last_error = exc
    return None, ProviderCall(
        provider=provider,
        operation=operation,
        status="failed",
        latency_ms=int((time.perf_counter() - started) * 1000),
        error=(
            f"{type(last_error).__name__}: {last_error}"
            if last_error is not None
            else "typed LLM operation failed"
        ),
    )


__all__ = [
    "SupplyChainAnalysisClient",
    "build_supply_chain_llm_client",
    "call_with_trace",
]
