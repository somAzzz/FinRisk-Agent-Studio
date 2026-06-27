"""DeepSeek API client.

The DeepSeek public API is OpenAI-compatible — see
https://api-docs.deepseek.com — so the same ``openai`` SDK we use for
``sglang`` and ``vllm`` works here. The only differences are:

- Base URL: ``https://api.deepseek.com``
- Auth: a real Bearer token (``DEEPSEEK_API_KEY``)
- Default model: ``deepseek-chat`` (non-reasoning) or
  ``deepseek-reasoner`` (chain-of-thought)

The client exposes two surfaces:

- :meth:`DeepSeekClient.complete` for plain chat completions.
- :meth:`DeepSeekClient.extract_risks` for the structured risk
  extraction prompt the FinText-LLM pipeline already uses; the
  output is the same dict shape as :class:`EdgarLLMClient` so the
  caller can swap providers without changing downstream code.

The module is lazy: importing it does not require ``DEEPSEEK_API_KEY``
to be set. ``complete`` / ``extract_risks`` raise
:class:`DeepSeekNotConfigured` when the key is missing or still a
placeholder, so demo / CI runs fail loudly rather than silently
sending traffic to the real API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI

from src.llm.tool_loop import OpenAICompatibleToolLoop, ToolFunction, ToolLoopError
from src.schemas.finrisk import LLMCall
from src.schemas.tool_trace import ToolBudgetUsage, ToolExecutionEvent

logger = logging.getLogger(__name__)


# Defaults match the values published at https://api-docs.deepseek.com.
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TIMEOUT_S = 60.0
MAX_INPUT_TOKENS = 1500


class DeepSeekError(Exception):
    """Base exception for DeepSeek client errors."""


class DeepSeekNotConfigured(DeepSeekError):  # noqa: N818
    """Raised when ``DEEPSEEK_API_KEY`` is missing or a placeholder."""


_PLACEHOLDER_KEYS = frozenset(
    {"", "empty", "dummy", "replace_me", "replace-me-with-your-deepseek-api-key"}
)


def _is_placeholder_key(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.strip().lower()
    if lowered in _PLACEHOLDER_KEYS:
        return True
    return lowered.startswith("replace-me")


class DeepSeekClient:
    """Thin wrapper around the OpenAI SDK for the DeepSeek public API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        *,
        llm_call_sink: Callable[[LLMCall], None] | None = None,
    ) -> None:
        resolved_base = (
            base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or DEFAULT_BASE_URL
        )
        resolved_key = (
            api_key if api_key is not None
            else os.environ.get("DEEPSEEK_API_KEY")
        )
        if _is_placeholder_key(resolved_key):
            # We still build the SDK client so the import + unit
            # tests that mock the client work. The first call will
            # raise DeepSeekNotConfigured.
            self._configured = False
            resolved_key = resolved_key or "missing"
        else:
            self._configured = True
        self.model = model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.client = OpenAI(
            base_url=resolved_base,
            api_key=resolved_key,
            timeout=timeout_s,
        )
        self.base_url = resolved_base
        self._llm_call_sink: Callable[[LLMCall], None] = (
            llm_call_sink or (lambda _c: None)
        )
        self.provider = "deepseek"
        self.last_tool_events: list[ToolExecutionEvent] = []
        self.last_tool_budget_usage: ToolBudgetUsage | None = None

    # -- audit helpers ----------------------------------------------------

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        step_name: str,
        chunk_id: str | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> tuple[str, LLMCall]:
        """Run a chat completion and emit a :class:`LLMCall` row.

        Mirrors :meth:`EdgarLLMClient._chat` so the workflow state has
        identical audit rows regardless of provider.
        """
        started = datetime.now(tz=UTC)
        call_id = f"ds-{uuid.uuid4().hex[:12]}"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
            )
        except Exception as exc:
            completed = datetime.now(tz=UTC)
            latency_ms = int((completed - started).total_seconds() * 1000)
            call = LLMCall(
                call_id=call_id,
                step_name=step_name,
                chunk_id=chunk_id,
                provider=self.provider,
                model=self.model,
                messages=messages,
                prompt_text=messages[-1]["content"] if messages else "",
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started,
                completed_at=completed,
            )
            self._llm_call_sink(call)
            raise
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        completed = datetime.now(tz=UTC)
        latency_ms = int((completed - started).total_seconds() * 1000)
        call = LLMCall(
            call_id=call_id,
            step_name=step_name,
            chunk_id=chunk_id,
            provider=self.provider,
            model=self.model,
            messages=list(messages),
            prompt_text=messages[-1]["content"] if messages else "",
            response_text=content,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            latency_ms=latency_ms,
            started_at=started,
            completed_at=completed,
        )
        self._llm_call_sink(call)
        return content, call

    @property
    def configured(self) -> bool:
        """Return ``True`` if a real API key is present."""
        return self._configured

    # ------------------------------------------------------------------
    # Low-level: chat completion
    # ------------------------------------------------------------------

    def _ensure_configured(self) -> None:
        if not self._configured:
            raise DeepSeekNotConfigured(
                "DEEPSEEK_API_KEY is not set or is a placeholder; "
                "apply for a key at https://platform.deepseek.com and "
                "export it before calling DeepSeek."
            )

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Return the model's plain-text response for ``prompt``."""
        self._ensure_configured()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            content, _call = self._chat(
                messages,
                step_name="deepseek_complete",
                chunk_id=None,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            return ""
        return content

    def complete_with_tools(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]],
        tool_map: Mapping[str, ToolFunction],
        system: str | None = None,
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
        max_tool_result_chars: int | None = None,
        max_total_tool_result_chars: int | None = None,
    ) -> str:
        """Run an OpenAI-compatible tool-calling loop.

        DeepSeek returns requested tool calls but never executes local
        functions itself. This method implements the application-side loop:
        send ``tools``, execute only functions present in ``tool_map``, append
        ``role="tool"`` messages, then ask the model for the final answer.
        """
        self._ensure_configured()
        loop = self._tool_loop()
        try:
            content = loop.complete(
                prompt,
                tools=tools,
                tool_map=tool_map,
                system=system,
                max_tool_rounds=max_tool_rounds,
                max_tokens=max_tokens,
                temperature=temperature,
                tool_choice=tool_choice,
                extra_body=extra_body,
                max_tool_result_chars=max_tool_result_chars,
                max_total_tool_result_chars=max_total_tool_result_chars,
            )
            self.last_tool_events = loop.last_tool_events
            self.last_tool_budget_usage = loop.last_budget_usage
            return content
        except ToolLoopError as exc:
            raise DeepSeekError(str(exc)) from exc

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_map: Mapping[str, ToolFunction],
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
        max_tool_result_chars: int | None = None,
        max_total_tool_result_chars: int | None = None,
    ) -> tuple[str, list[LLMCall]]:
        """Return ``(final_text, audit_calls)`` after resolving tool calls.

        Unknown tools and invalid JSON arguments are returned to the model as
        tool error messages; they are never executed.
        """
        self._ensure_configured()
        loop = self._tool_loop()
        try:
            content, calls = loop.chat(
                messages,
                tools=tools,
                tool_map=tool_map,
                max_tool_rounds=max_tool_rounds,
                max_tokens=max_tokens,
                temperature=temperature,
                tool_choice=tool_choice,
                extra_body=extra_body,
                max_tool_result_chars=max_tool_result_chars,
                max_total_tool_result_chars=max_total_tool_result_chars,
            )
            self.last_tool_events = loop.last_tool_events
            self.last_tool_budget_usage = loop.last_budget_usage
            return content, calls
        except ToolLoopError as exc:
            raise DeepSeekError(str(exc)) from exc

    def _tool_loop(self) -> OpenAICompatibleToolLoop:
        return OpenAICompatibleToolLoop(
            client=self.client,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            llm_call_sink=self._llm_call_sink,
            step_name="deepseek_tool_calling",
        )

    # ------------------------------------------------------------------
    # High-level: structured risk extraction
    # ------------------------------------------------------------------

    def extract_risks(
        self,
        section_1a: str,
        company_name: str = "Unknown",
        year: int = 2020,
    ) -> dict[str, Any]:
        """Extract risks from a 10-K Item 1A section (legacy dict shape).

        Returns a dict in the same shape as
        :meth:`src.llm.client.EdgarLLMClient.extract_risks` so
        callers can switch providers without rewriting downstream
        code. Prefer :meth:`extract_risks_chunked` for new code.
        """
        if not section_1a or not section_1a.strip():
            raise ValueError("section_1a cannot be empty or None")
        self._ensure_configured()
        # The legacy path uses one chat per call and truncates to
        # DEFAULT_CHUNK_SIZE; the chunked variant below handles long
        # sections properly.
        prompt = self._build_prompt(section_1a, company_name)
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        try:
            content, _call = self._chat(
                messages,
                step_name="deepseek_extract_risks",
                chunk_id=None,
                max_tokens=None,
                temperature=None,
            )
        except Exception:
            return {
                "company": company_name,
                "year": year,
                "risks": [],
                "avg_severity": 0,
                "raw_response": "",
                "error": "LLM call failed",
            }
        return self._parse_response(content, company_name, year)

    def _build_prompt(self, section_1a: str, company_name: str) -> str:
        """Build the structured-output prompt for risk extraction."""
        # ``section_1a`` is already truncated to one chunk's worth of
        # text by the caller (legacy dict-shape API only sees one chunk).
        return (
            "Output only valid JSON in a code block. No thinking.\n\n"
            f"Extract risks from 10-K Item 1A.\n\n"
            f"Company: {company_name}\n"
            f"Text: {section_1a}"
        )

    def _parse_response(
        self,
        content: str,
        company_name: str,
        year: int,
    ) -> dict[str, Any]:
        """Parse the LLM response into the canonical risk-extraction shape."""
        # Markdown code block first.
        json_in_markdown = re.findall(
            r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content
        )
        for json_str in json_in_markdown:
            try:
                result = json.loads(json_str)
                if "risks" in result or "risk" in result:
                    return self._normalize_result(result, company_name, year)
            except json.JSONDecodeError:
                continue

        # Bare JSON.
        try:
            result = json.loads(content)
            return self._normalize_result(result, company_name, year)
        except json.JSONDecodeError:
            pass

        # Last resort: scan for any JSON-like object in the text.
        for candidate in re.findall(
            r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content
        )[::-1]:
            try:
                result = json.loads(candidate)
                if "risks" in result or "risk" in result:
                    return self._normalize_result(result, company_name, year)
            except json.JSONDecodeError:
                continue

        return {
            "company": company_name,
            "year": year,
            "risks": [],
            "avg_severity": 0,
            "raw_response": content[:500],
        }

    def _normalize_result(
        self,
        result: dict[str, Any],
        company_name: str,
        year: int,
    ) -> dict[str, Any]:
        """Match the v15 dict shape: ``risks[*].risk_factor / severity / quote``."""
        if "risk" in result and "risks" not in result:
            result["risks"] = result.pop("risk")

        if "risks" in result:
            normalized: list[dict[str, Any]] = []
            for risk in result["risks"]:
                if isinstance(risk, str):
                    normalized.append(
                        {"risk_factor": risk, "severity": 3, "quote": ""}
                    )
                elif isinstance(risk, dict):
                    rf = (
                        risk.get("risk_factor")
                        or risk.get("description")
                        or risk.get("risk")
                        or "Unknown"
                    )
                    sev = risk.get("severity", risk.get("risk_level", 3))
                    q = risk.get("quote", risk.get("text", ""))
                    normalized.append(
                        {"risk_factor": rf, "severity": sev, "quote": q}
                    )
            result["risks"] = normalized

        result["company"] = company_name
        result["year"] = year
        if "avg_severity" not in result and result.get("risks"):
            severities = [
                r.get("severity", 3)
                for r in result["risks"]
                if isinstance(r, dict)
            ]
            if severities:
                result["avg_severity"] = round(
                    sum(severities) / len(severities), 2
                )
        return result


def build_client_from_settings() -> DeepSeekClient:
    """Construct a :class:`DeepSeekClient` from :func:`src.config.get_settings`.

    Centralises the wiring so other modules (and tests) do not duplicate
    the env-var lookups.
    """
    from src.config import get_settings

    settings = get_settings()
    return DeepSeekClient(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        timeout_s=settings.deepseek_timeout_s,
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT_S",
    "DeepSeekClient",
    "DeepSeekError",
    "DeepSeekNotConfigured",
    "ToolFunction",
    "build_client_from_settings",
]
