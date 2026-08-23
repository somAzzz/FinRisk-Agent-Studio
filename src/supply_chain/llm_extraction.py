"""LLM extraction helpers for real-mode supply-chain discovery.

Search is used to collect candidate public evidence. This module asks
the selected LLM backend to read those snippets and return structured
supplier relations, then validates the response before the graph step
turns it into nodes and edges.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.llm_config import LLMRunConfig

SupplyChainLLMRelationType = Literal[
    "supplied_by",
    "depends_on",
    "manufactured_by",
    "hosted_on",
    "powered_by",
    "enabled_by",
    "hypothesized",
]


class SupplyChainLLMClient(Protocol):
    """Small protocol shared by OpenAI-compatible and test clients."""

    provider: str
    model: str

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Return a plain-text chat completion."""


class SupplierRelationExtraction(BaseModel):
    """One Pydantic-validated supplier relation emitted by the LLM."""

    model_config = ConfigDict(extra="ignore")

    supplier_name: str = Field(min_length=1)
    ticker: str | None = None
    relation_type: SupplyChainLLMRelationType = "supplied_by"
    component: str | None = None
    source_index: int = Field(default=1, ge=1, le=20)
    source_url: str | None = None
    quote: str = Field(min_length=1)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    rationale: str | None = None

    @field_validator("supplier_name", "quote", mode="before")
    @classmethod
    def _strip_required(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("ticker", "component", "source_url", "rationale", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


def build_supply_chain_llm_client(
    llm_config: LLMRunConfig | None,
) -> Any:
    """Build the selected per-run LLM client for supply-chain extraction."""
    config = llm_config or LLMRunConfig()
    from src.config import get_settings

    settings = get_settings()
    if settings.agent_runtime_mode == "pydantic_ai_primary":
        from src.ai.deps import AgentServices
        from src.ai.model_factory import (
            build_agent_model,
            resolve_agent_model_config,
        )
        from src.ai.store_factory import get_agent_run_recorder
        from src.ai.structured_clients import PydanticAISupplierRelationClient

        return PydanticAISupplierRelationClient(
            model=build_agent_model(
                resolve_agent_model_config(config, settings=settings)
            ),
            settings=settings,
            services=AgentServices(
                message_recorder=get_agent_run_recorder()
            ),
        )
    provider = config.provider
    if provider == "deepseek":
        from src.llm.deepseek_client import DeepSeekClient

        return DeepSeekClient(
            base_url=config.base_url,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )

    from src.llm.client import EdgarLLMClient

    defaults = {
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
    base_url, api_key, model = defaults.get(provider, defaults["sglang"])
    return EdgarLLMClient(
        base_url=config.base_url or base_url,
        api_key=api_key,
        model=model,
        provider=provider,
    )


def extract_supplier_relations(
    client: SupplyChainLLMClient,
    *,
    company_name: str | None,
    product_name: str,
    source_label: str,
    search_query: str,
    search_results: list[Any],
    max_suppliers: int,
) -> tuple[list[SupplierRelationExtraction], str]:
    """Ask an LLM to extract structured supplier relations from snippets."""
    if not search_results:
        return [], ""
    prompt = _build_prompt(
        company_name=company_name,
        product_name=product_name,
        source_label=source_label,
        search_query=search_query,
        search_results=search_results,
        max_suppliers=max_suppliers,
    )
    typed_extract = getattr(client, "extract_supplier_relations", None)
    if callable(typed_extract):
        return typed_extract(
            prompt=prompt,
            company_name=company_name,
            product_name=product_name,
            max_suppliers=max_suppliers,
        )
    content = client.complete(
        prompt,
        system=(
            "You extract evidence-backed supply-chain relationships from web "
            "search snippets. Use only the provided snippets. Return JSON only."
        ),
        max_tokens=1800,
        temperature=0.0,
    )
    payload = _extract_json(content)
    raw_relations = _raw_relations(payload)
    relations: list[SupplierRelationExtraction] = []
    for raw in raw_relations:
        if not isinstance(raw, dict):
            continue
        try:
            relation = SupplierRelationExtraction.model_validate(raw)
        except Exception:
            continue
        relations.append(relation)
        if len(relations) >= max_suppliers:
            break
    return relations, content


def _build_prompt(
    *,
    company_name: str | None,
    product_name: str,
    source_label: str,
    search_query: str,
    search_results: list[Any],
    max_suppliers: int,
) -> str:
    snippets: list[str] = []
    for index, result in enumerate(search_results[:8], start=1):
        title = getattr(result, "title", "") or ""
        url = getattr(result, "url", "") or ""
        snippet = getattr(result, "snippet", "") or ""
        snippets.append(
            f"[{index}]\nTitle: {title}\nURL: {url}\nSnippet: {snippet}"
        )
    evidence_block = "\n\n".join(snippets)
    company = company_name or "Unknown company"
    return f"""Company: {company}
Product: {product_name}
Current graph node to expand: {source_label}
Search query: {search_query}

Extract up to {max_suppliers} supplier/provider/manufacturer relationships that are directly supported by the snippets.

Rules:
- Do not infer a supplier from brand recognition alone.
- Every relation must include a short quote copied from one snippet.
- Use source_index to point at the snippet that supports the quote.
- If the evidence is weak or indirect, use relation_type "hypothesized" and confidence below 0.55.
- Prefer relation_type values: supplied_by, manufactured_by, hosted_on,
  powered_by, enabled_by, depends_on, hypothesized.
- If no relationship is supported, return {{"relations": []}}.

Return ONLY JSON:
{{
  "relations": [
    {{
      "supplier_name": "Company name",
      "ticker": "Optional ticker",
      "relation_type": "supplied_by",
      "component": "component or service",
      "source_index": 1,
      "source_url": "https://...",
      "quote": "verbatim support quote",
      "confidence": 0.0,
      "rationale": "brief reason"
    }}
  ]
}}

Snippets:
{evidence_block}
"""


def _raw_relations(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    raw = payload.get("relations") or payload.get("suppliers") or payload.get("edges")
    return raw if isinstance(raw, list) else []


def _extract_json(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min(
        [idx for idx in (text.find("{"), text.find("[")) if idx >= 0],
        default=-1,
    )
    if start < 0:
        return None
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


__all__ = [
    "SupplierRelationExtraction",
    "SupplyChainLLMClient",
    "build_supply_chain_llm_client",
    "extract_supplier_relations",
]
