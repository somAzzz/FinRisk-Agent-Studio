"""LLM extraction helpers for real-mode supply-chain discovery.

Search is used to collect candidate public evidence. This module asks
the selected LLM backend to read those snippets and return structured
supplier relations, then validates the response before the graph step
turns it into nodes and edges.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupplyChainLLMRelationType = Literal[
    "supplied_by",
    "depends_on",
    "manufactured_by",
    "hosted_on",
    "powered_by",
    "enabled_by",
    "hypothesized",
]


class SupplierRelationExtraction(BaseModel):
    """One Pydantic-validated supplier relation emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

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


class SupplyChainRelationClient(Protocol):
    """Typed relation extraction operation required by supplier discovery."""

    def extract_supplier_relations(
        self,
        *,
        prompt: str,
        company_name: str | None,
        product_name: str,
        max_suppliers: int,
    ) -> tuple[list[SupplierRelationExtraction], str]: ...


def extract_supplier_relations(
    client: SupplyChainRelationClient,
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
    return client.extract_supplier_relations(
        prompt=prompt,
        company_name=company_name,
        product_name=product_name,
        max_suppliers=max_suppliers,
    )


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


__all__ = [
    "SupplierRelationExtraction",
    "SupplyChainRelationClient",
    "extract_supplier_relations",
]
