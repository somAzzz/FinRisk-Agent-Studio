"""LLM client for risk extraction from EDGAR filings.

The OpenAI-compatible family (sglang / vllm / openai) all share this
client. The client is the source of truth for risk extraction and
provides:

* :meth:`EdgarLLMClient.extract_risks_chunked` — the canonical Map-style
  extractor. Splits the input section into overlapping chunks via
  :func:`chunk_text` (default 4000 chars / 400 overlap), runs one LLM
  call per chunk, validates every item against the
  :class:`ExtractedRisk` schema, and returns a deduplicated risk list
  alongside per-chunk :class:`ChunkValidation` and per-call
  :class:`LLMCall` audit rows.
* :meth:`EdgarLLMClient.complete` / :meth:`summarize` / :meth:`decide_action`
  — general-purpose helpers used by :class:`MarketExplorer` and the
  browser exploration step.
* :meth:`EdgarLLMClient.compute_embedding` — sentence-transformers
  wrapper for novelty detection.

The LLMCall sink is injected via ``llm_call_sink``. The workflow's
``FilingRiskExtractorStep`` passes a sink that appends each
:class:`LLMCall` to ``state.llm_log`` so the frontend inspector can
render the full chat history.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from src.agents.extraction_agent import chunk_text
from src.llm.sglang_client import BrowserAction
from src.llm.tool_loop import OpenAICompatibleToolLoop, ToolFunction, ToolLoopError
from src.schemas.finrisk import ChunkValidation, ExtractedRisk, LLMCall

DEFAULT_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
DEFAULT_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 2000

# Default chunking parameters for risk extraction. 4000 chars ≈ 1000
# tokens for English text — comfortably inside every supported model's
# context. Override per-call via the ``chunk_size``/``overlap`` kwargs.
DEFAULT_CHUNK_SIZE = 4000
DEFAULT_CHUNK_OVERLAP = 400

# A small sink that drops calls on the floor — the default no-op so the
# client can be constructed without a state object.
NoOpSink = Callable[[LLMCall], None]


def _no_sink(_call: LLMCall) -> None:
    """Default no-op sink used when no caller-supplied sink is provided."""


class RiskExtractorError(Exception):
    """Base exception for risk extraction errors."""


class EdgarLLMClient:
    """Client for extracting risks from EDGAR filings using the
    OpenAI-compatible chat-completions API (sglang / vllm / openai).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        *,
        llm_call_sink: NoOpSink | None = None,
        provider: str = "vllm",
    ) -> None:
        self.client = OpenAI(
            base_url=base_url or DEFAULT_BASE_URL,
            api_key=(
                api_key if api_key is not None
                else os.environ.get("VLLM_API_KEY", "dummy")
            ),
        )
        self.model = model or DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._llm_call_sink: NoOpSink = llm_call_sink or _no_sink
        self.provider = provider

    # -- core chat helper -------------------------------------------------

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        step_name: str,
        chunk_id: str | None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, LLMCall]:
        """Call chat-completions and return ``(content, audit_row)``.

        The audit row is emitted via ``self._llm_call_sink`` after the
        call returns (success or failure), so callers always see a
        corresponding ``LLMCall`` in the workflow state.
        """
        started = datetime.now(tz=UTC)
        call_id = f"llm-{uuid.uuid4().hex[:12]}"
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
                response_text="",
                response_structured=None,
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started,
                completed_at=completed,
            )
            self._llm_call_sink(call)
            raise
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
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
            response_structured=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            error=None,
            started_at=started,
            completed_at=completed,
        )
        self._llm_call_sink(call)
        return content, call

    # -- chunked risk extraction (canonical entry point) ------------------

    def extract_risks_chunked(
        self,
        section_1a: str,
        company_name: str = "Unknown",
        year: int = 2020,
        *,
        source_id: str = "unknown",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        step_name: str = "filing_risk_extractor",
    ) -> tuple[list[ExtractedRisk], list[ChunkValidation], list[LLMCall]]:
        """Extract risks from a long section via Map over chunks.

        Each chunk goes through ``extract_risks_single_chunk`` which
        validates the LLM response against the :class:`ExtractedRisk`
        schema and emits one :class:`ChunkValidation` per chunk.

        Args:
            section_1a: Full Item 1A text (possibly tens of thousands
                of characters). Will be chunked — no truncation.
            company_name: For prompt context and Pydantic default.
            year: For prompt context and Pydantic default.
            source_id: Stable identifier for the source (typically the
                SEC accession number) — propagated to
                :class:`ExtractedRisk.source` and used as the
                ``source_id`` argument of :func:`chunk_text`.
            chunk_size: Characters per chunk (default 4000).
            overlap: Characters of overlap between adjacent chunks
                (default 400).
            step_name: Forwarded to each emitted :class:`LLMCall` so
                the workflow inspector can filter per step.

        Returns:
            ``(deduped_risks, chunk_validations, llm_calls)``.

        Raises:
            ValueError: if ``section_1a`` is empty.
        """
        if not section_1a or not section_1a.strip():
            raise ValueError("section_1a cannot be empty or None")

        chunks = chunk_text(
            text=section_1a,
            source_id=source_id,
            source_type="sec_filing",
            section="section_1a",
            chunk_size=chunk_size,
            overlap=overlap,
        )
        all_risks: list[ExtractedRisk] = []
        all_validations: list[ChunkValidation] = []
        all_calls: list[LLMCall] = []
        for chunk in chunks:
            risks, validation, call = self.extract_risks_single_chunk(
                chunk.text,
                company_name=company_name,
                year=year,
                chunk_id=chunk.chunk_id,
                section_name="section_1a",
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                step_name=step_name,
            )
            all_risks.extend(risks)
            all_validations.append(validation)
            all_calls.append(call)
        deduped = self._dedupe_risks(all_risks)
        return deduped, all_validations, all_calls

    def extract_risks_single_chunk(
        self,
        chunk_text: str,
        *,
        company_name: str,
        year: int,
        chunk_id: str,
        section_name: str | None,
        char_start: int | None,
        char_end: int | None,
        step_name: str = "filing_risk_extractor",
    ) -> tuple[list[ExtractedRisk], ChunkValidation, LLMCall]:
        """Extract and Pydantic-validate risks from one chunk.

        Returns ``(validated_risks, validation_row, llm_call_row)``.
        Even on parse failure the validation_row and llm_call_row are
        populated so the inspector can see what went wrong.
        """
        started = datetime.now(tz=UTC)
        prompt = self._build_risk_prompt(chunk_text, company_name, year)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _RISK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            content, call = self._chat(
                messages,
                step_name=step_name,
                chunk_id=chunk_id,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            validation = ChunkValidation(
                chunk_id=chunk_id,
                pydantic_model="ExtractedRisk",
                ok=False,
                errors=[f"{type(exc).__name__}: {exc}"],
                validated_count=0,
                dropped_count=0,
                fallback_used=None,
                section_name=section_name,
                char_start=char_start,
                char_end=char_end,
                validated_at=datetime.now(tz=UTC),
            )
            return [], validation, _placeholder_call(
                call_id=f"err-{uuid.uuid4().hex[:8]}",
                step_name=step_name,
                chunk_id=chunk_id,
                provider=self.provider,
                model=self.model,
                prompt_text=prompt,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started,
            )

        # Persist the structured response alongside the raw text so the
        # inspector can render either.
        if call.response_structured is None and content:
            structured = _extract_risk_payload(content)
            if structured is not None:
                call = call.model_copy(update={"response_structured": structured})
                self._llm_call_sink(call)

        risks, errors = self._coerce_risks(content, company_name, year)
        validation = ChunkValidation(
            chunk_id=chunk_id,
            pydantic_model="ExtractedRisk",
            ok=not errors,
            errors=errors,
            validated_count=len(risks),
            dropped_count=0 if not errors else max(0, errors and 0),
            fallback_used="llm",
            section_name=section_name,
            char_start=char_start,
            char_end=char_end,
            validated_at=datetime.now(tz=UTC),
        )
        # Patch the per-chunk call with the validated_count + a preview.
        call = call.model_copy(update={"response_structured": {
            "validated_count": len(risks),
            "first_risk": risks[0].risk_factor[:120] if risks else "",
            "errors": errors[:3],
        }})
        self._llm_call_sink(call)
        return risks, validation, call

    # -- one-shot (legacy) entry point ------------------------------------

    def extract_risks(
        self,
        section_1a: str,
        company_name: str = "Unknown",
        year: int = 2020,
    ) -> dict[str, Any]:
        """Single-shot extractor (legacy). Returns a raw dict.

        The FinRisk workflow should prefer
        :meth:`extract_risks_chunked` so the LLM sees the entire
        section. This method is kept for the MVP ``analyze_company``
        path and for external callers that want a dict shape.
        """
        if not section_1a or not section_1a.strip():
            raise ValueError("section_1a cannot be empty or None")

        prompt = self._build_risk_prompt(section_1a[:DEFAULT_CHUNK_SIZE], company_name, year)
        messages = [
            {"role": "system", "content": _RISK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            content, _call = self._chat(
                messages,
                step_name="analyze_company_mvp",
                chunk_id=None,
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
        risks, errors = self._coerce_risks(content, company_name, year)
        return {
            "company": company_name,
            "year": year,
            "risks": [
                {
                    "risk_factor": r.risk_factor,
                    "severity": r.severity,
                    "quote": r.evidence_quote,
                }
                for r in risks
            ],
            "avg_severity": round(sum(r.severity for r in risks) / max(1, len(risks)), 2),
            "raw_response": content[:500],
            "errors": errors,
        }

    # -- general chat helpers --------------------------------------------

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """General-purpose chat completion (returns raw text, no audit row)."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            content, _call = self._chat(
                messages,
                step_name="complete",
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
    ) -> str:
        """General-purpose OpenAI-compatible tool-calling completion.

        This is the local/vLLM/SGLang counterpart to
        :meth:`DeepSeekClient.complete_with_tools`. It assumes the configured
        local server supports OpenAI-compatible ``tools`` / ``tool_calls``.
        """
        try:
            return self._tool_loop().complete(
                prompt,
                tools=tools,
                tool_map=tool_map,
                system=system,
                max_tool_rounds=max_tool_rounds,
                max_tokens=max_tokens,
                temperature=temperature,
                tool_choice=tool_choice,
                extra_body=extra_body,
            )
        except ToolLoopError as exc:
            raise RiskExtractorError(str(exc)) from exc

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
    ) -> tuple[str, list[LLMCall]]:
        """Return ``(final_text, audit_calls)`` after resolving tool calls."""
        try:
            return self._tool_loop().chat(
                messages,
                tools=tools,
                tool_map=tool_map,
                max_tool_rounds=max_tool_rounds,
                max_tokens=max_tokens,
                temperature=temperature,
                tool_choice=tool_choice,
                extra_body=extra_body,
            )
        except ToolLoopError as exc:
            raise RiskExtractorError(str(exc)) from exc

    def _tool_loop(self) -> OpenAICompatibleToolLoop:
        return OpenAICompatibleToolLoop(
            client=self.client,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            llm_call_sink=self._llm_call_sink,
            step_name="local_tool_calling",
        )

    def summarize(self, content: str) -> str:
        """Summarize browser page content for market exploration."""
        if not content:
            return ""
        prompt = (
            "Summarize this financial web page in 2-3 concise sentences. "
            "Focus on facts relevant to the user's market research task.\n\n"
            f"{content[:5000]}"
        )
        try:
            return self.complete(
                prompt,
                system="You are a financial research assistant.",
                max_tokens=256,
                temperature=0.1,
            ).strip()
        except Exception:
            return content[:200]

    def decide_action(
        self,
        goal: str,
        visited_urls: list[str],
        recent_findings: list[tuple[str, str]],
    ) -> BrowserAction | None:
        """Decide the next browser action for ``MarketExplorer``."""
        visited_str = ", ".join(visited_urls[:5])
        findings_str = "; ".join(
            f"{summary} ({url})" for summary, url in recent_findings[-3:]
        )
        prompt = f"""Goal: {goal}

Visited URLs: {visited_str}
Recent findings: {findings_str}

Choose the next browser action. Respond only as JSON with keys:
thought, action, query, url, selector.
Allowed actions: search, navigate, click, scroll, stop."""
        try:
            raw = self.complete(
                prompt,
                system="You are a web browsing assistant. Output only JSON.",
                max_tokens=256,
                temperature=0.1,
            )
            payload = _extract_json_object(raw)
            if payload is None:
                return None
            return BrowserAction.model_validate(payload)
        except Exception:
            return None

    def compute_embedding(self, text: str) -> list[float]:
        """Compute text embedding for novelty detection."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text).tolist()

    # -- internal helpers ------------------------------------------------

    @staticmethod
    def _build_risk_prompt(section_text: str, company_name: str, year: int) -> str:
        """Build the risk-extraction prompt (no truncation, no thinking)."""
        return (
            f"Company: {company_name}\n"
            f"Filing year: {year}\n"
            f"Source: 10-K Item 1A. Risk Factors (excerpt)\n\n"
            "Extract every distinct macro/policy/operational/financial "
            "risk factor from the text below. Each risk MUST be backed "
            "by a verbatim quote from the source text.\n\n"
            "Output ONLY a JSON object of this shape:\n"
            "{\n"
            '  "risks": [\n'
            '    {"risk_factor": "<short name>",\n'
            '     "severity": <integer 1..5>,\n'
            '     "quote": "<verbatim quote from text>"}\n'
            "  ]\n"
            "}\n\n"
            f"Text:\n\"\"\"\n{section_text}\n\"\"\"\n"
        )

    @staticmethod
    def _coerce_risks(
        content: str,
        company_name: str,
        year: int,
    ) -> tuple[list[ExtractedRisk], list[str]]:
        """Parse LLM content into Pydantic-validated ``ExtractedRisk`` rows.

        Returns ``(valid_rows, error_messages)``. Items that fail
        Pydantic validation are dropped (counted in error_messages)
        rather than crashing the chunk.
        """
        payload = _extract_risk_payload(content)
        if payload is None:
            return [], ["llm returned no parseable JSON"]
        raw_risks = payload.get("risks") or payload.get("risk") or []
        if not isinstance(raw_risks, list):
            return [], [f"unexpected risks type: {type(raw_risks).__name__}"]

        valid: list[ExtractedRisk] = []
        errors: list[str] = []
        for index, raw in enumerate(raw_risks):
            if isinstance(raw, str):
                item = {"risk_factor": raw, "severity": 3, "quote": ""}
            else:
                item = raw
            if not isinstance(item, dict):
                errors.append(f"item {index}: not a dict or string")
                continue
            risk_factor = (
                item.get("risk_factor")
                or item.get("description")
                or item.get("risk")
                or ""
            )
            quote = item.get("quote") or item.get("text") or ""
            severity_raw = item.get("severity", item.get("risk_level", 3))
            try:
                severity = int(severity_raw)
            except (TypeError, ValueError):
                severity = 3
            try:
                valid.append(
                    ExtractedRisk(
                        risk_id=f"risk-{uuid.uuid4().hex[:8]}",
                        risk_factor=str(risk_factor).strip() or "Unknown",
                        severity=max(1, min(5, severity)),
                        evidence_quote=str(quote).strip(),
                        source="section_1a",
                        filing_section="section_1a",
                        confidence=0.6,
                    )
                )
            except ValidationError as exc:
                errors.append(f"item {index}: {exc.errors()[0]['msg']}")
        return valid, errors

    @staticmethod
    def _dedupe_risks(risks: list[ExtractedRisk]) -> list[ExtractedRisk]:
        """Deduplicate ``ExtractedRisk`` rows by case-insensitive
        ``risk_factor`` containment (longer risk_factor wins).
        """
        if not risks:
            return []
        sorted_risks = sorted(risks, key=lambda r: -len(r.risk_factor))
        kept: list[ExtractedRisk] = []
        for risk in sorted_risks:
            rf_lower = risk.risk_factor.lower()
            if any(
                rf_lower in kept_risk.risk_factor.lower()
                and kept_risk.risk_factor.lower() != rf_lower
                for kept_risk in kept
            ):
                continue
            kept.append(risk)
        return kept


# ---------------------------------------------------------------------------
# Module-level constants and helpers
# ---------------------------------------------------------------------------

_RISK_SYSTEM_PROMPT = (
    "You are a senior financial-risk analyst extracting risks from "
    "a single chunk of a 10-K Item 1A Risk Factors section. Output ONLY "
    "a JSON object with a top-level 'risks' array. Each entry must have "
    "'risk_factor' (short name), 'severity' (integer 1-5), and 'quote' "
    "(verbatim from the supplied text). Do not invent quotes."
)


def _placeholder_call(
    *,
    call_id: str,
    step_name: str,
    chunk_id: str,
    provider: str,
    model: str,
    prompt_text: str,
    error: str,
    started_at: datetime,
) -> LLMCall:
    """Build a placeholder :class:`LLMCall` row for failed chats."""
    completed = datetime.now(tz=UTC)
    latency_ms = max(0, int((completed - started_at).total_seconds() * 1000))
    return LLMCall(
        call_id=call_id,
        step_name=step_name,
        chunk_id=chunk_id,
        provider=provider,
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        prompt_text=prompt_text,
        response_text="",
        response_structured=None,
        latency_ms=latency_ms,
        error=error,
        started_at=started_at,
        completed_at=completed,
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model response."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    code_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    for block in code_blocks:
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_risk_payload(text: str) -> dict[str, Any] | None:
    """Find the JSON ``{risks: [...]}`` payload in a chat response."""
    payload = _extract_json_object(text)
    if payload is None:
        return None
    if "risks" in payload or "risk" in payload:
        return payload
    return None


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "EdgarLLMClient",
    "NoOpSink",
    "RiskExtractorError",
]
