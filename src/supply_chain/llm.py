"""LLM helpers for real supply-chain investigation steps."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.models import ProviderCall


def build_supply_chain_llm_client(config: LLMRunConfig | None) -> Any | None:
    """Return a configured chat client for supply-chain LLM steps."""
    resolved = config or LLMRunConfig()
    try:
        if resolved.provider == "deepseek":
            from src.llm.deepseek_client import DeepSeekClient

            return DeepSeekClient(
                base_url=resolved.base_url,
                model=resolved.model,
            )
        from src.llm.client import EdgarLLMClient

        defaults: dict[str, tuple[str, str, str]] = {
            "sglang": (
                os.environ.get("SGLANG_BASE_URL", "http://localhost:30000/v1"),
                os.environ.get("SGLANG_API_KEY", "EMPTY"),
                os.environ.get("SGLANG_MODEL", "Qwen/Qwen3.5-35B-A3B"),
            ),
            "vllm": (
                os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"),
                os.environ.get("VLLM_API_KEY", "dummy"),
                os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B"),
            ),
            "openai": (
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                os.environ.get("OPENAI_API_KEY", "REPLACE_ME"),
                os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            ),
        }
        base_url, api_key, model = defaults.get(resolved.provider, defaults["sglang"])
        return EdgarLLMClient(
            base_url=resolved.base_url or base_url,
            api_key=api_key,
            model=resolved.model or model,
            provider=resolved.provider,
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
) -> tuple[Any | None, ProviderCall]:
    """Call an LLM and parse a JSON object/array from the response."""
    started = time.perf_counter()
    try:
        content = client.complete(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
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
    "build_supply_chain_llm_client",
    "complete_json_with_trace",
    "extract_json",
]
