"""LLM helpers for real supply-chain investigation steps."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.ai.deps import AgentDeps, AgentServices, AgentSubject
from src.ai.model_factory import build_agent_model, resolve_agent_model_config
from src.ai.runtime_adapter import run_awaitable_sync
from src.ai.store_factory import get_agent_run_recorder
from src.config import Settings, get_settings
from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.models import ProviderCall


class PydanticAIJSONClient:
    """Small typed JSON boundary for supply-chain analysis prompts."""

    provider = "pydantic_ai"

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
    ) -> None:
        self._model = model
        self.model = model.model_name
        self.settings = settings
        self.services = services or AgentServices()

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        model_settings: dict[str, Any] = {}
        if max_tokens is not None:
            model_settings["max_tokens"] = max_tokens
        if temperature is not None:
            model_settings["temperature"] = temperature
        agent: Agent[AgentDeps, dict[str, Any]] = Agent(
            self._model,
            output_type=dict[str, Any],
            deps_type=AgentDeps,
            instructions=system or "Return one valid JSON object.",
            model_settings=model_settings or None,
            name="supply_chain_json_analysis",
        )
        run_id = f"supply-json-{uuid.uuid4().hex[:12]}"
        deps = AgentDeps(
            run_id=run_id,
            conversation_id=run_id,
            settings=self.settings,
            subject=AgentSubject(),
            services=self.services,
        )
        result = agent.run_sync(prompt, deps=deps, run_id=run_id)
        recorder = self.services.message_recorder
        if recorder is not None:
            run_awaitable_sync(
                recorder.record_result(
                    run_id=run_id,
                    conversation_id=run_id,
                    agent_name=agent.name or "supply_chain_json_analysis",
                    result=result,
                )
            )
        return json.dumps(result.output, ensure_ascii=False)


def build_supply_chain_llm_client(config: LLMRunConfig | None) -> Any | None:
    """Return a Pydantic AI client for supply-chain LLM steps."""
    resolved = config or LLMRunConfig()
    try:
        settings = get_settings()
        return PydanticAIJSONClient(
            model=build_agent_model(
                resolve_agent_model_config(resolved, settings=settings)
            ),
            settings=settings,
            services=AgentServices(message_recorder=get_agent_run_recorder()),
        )
    except Exception:
        return None


def complete_json_with_trace(
    *,
    client: Any,
    provider: str,
    operation: str,
    prompt: str,
    system: str,
    max_tokens: int = 1400,
    temperature: float = 0.1,
    retries: int = 1,
) -> tuple[Any | None, ProviderCall]:
    """Call an LLM and parse a JSON object/array from the response."""
    started = time.perf_counter()
    try:
        content = ""
        for attempt in range(max(1, retries + 1)):
            content = client.complete(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if content:
                break
            if attempt >= retries:
                break
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not content:
            return None, ProviderCall(
                provider=provider,
                operation=operation,
                status="failed",
                latency_ms=latency_ms,
                error="empty LLM response",
            )
        parsed = extract_json(content)
        if parsed is None:
            return None, ProviderCall(
                provider=provider,
                operation=operation,
                status="failed",
                latency_ms=latency_ms,
                error="LLM response did not contain complete JSON",
            )
        return parsed, ProviderCall(
            provider=provider,
            operation=operation,
            status="success",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return None, ProviderCall(
            provider=provider,
            operation=operation,
            status="failed",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )


def extract_json(content: str) -> Any | None:
    """Extract the first JSON object or array from an LLM response."""
    stripped = content.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.I)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    if stripped[0] in "[{":
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            parsed, _end = decoder.raw_decode(stripped[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


__all__ = [
    "PydanticAIJSONClient",
    "build_supply_chain_llm_client",
    "complete_json_with_trace",
    "extract_json",
]
