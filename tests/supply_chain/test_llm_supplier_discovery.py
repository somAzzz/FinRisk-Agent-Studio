"""LLM-driven supplier discovery migration tests."""

from __future__ import annotations

import json

from src.agents.llm_runtime import LLMToolRunResult
from src.schemas.tool_trace import ToolExecutionEvent
from src.supply_chain.models import SupplyChainExploreRequest
from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
from src.supply_chain.steps.requirement_decomposer import (
    SupplyChainRequirementDecomposerStep,
)
from src.supply_chain.steps.supplier_discovery import (
    SupplyChainSupplierDiscoveryStep,
)
from src.supply_chain.workflow import run_supply_chain_workflow
from src.tools.catalog import build_project_tool_catalog
from src.tools.providers.base import SearchResponse
from src.workflows.state import utcnow


class EmptyRouter:
    def search(self, query, intent="general", max_results=5):
        return SearchResponse(
            provider="stub",
            query=query,
            retrieved_at=utcnow(),
            results=[],
        )


def _event(payload: dict) -> ToolExecutionEvent:
    content = json.dumps(payload)
    return ToolExecutionEvent(
        event_id="event-web-search",
        round_id="round-0",
        tool_call_id="call-web-search",
        tool_name="web_search",
        arguments={"query": "OpenAI ChatGPT GPU supplier NVIDIA"},
        status="success",
        result_summary=content,
        latency_ms=1,
        result_chars=len(content),
        created_at=utcnow(),
    )


async def test_llm_supplier_discovery_shadow_records_candidates_without_edges() -> None:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "provider": "fake",
            "query": "OpenAI ChatGPT GPU supplier NVIDIA",
            "retrieved_at": utcnow().isoformat(),
            "results": [
                {
                    "title": "NVIDIA supplies GPUs for AI data centers",
                    "url": "https://www.reuters.com/technology/nvidia-ai-gpus",
                    "snippet": (
                        "NVIDIA H100 GPUs are used to power AI training "
                        "and inference workloads."
                    ),
                    "rank": 1,
                }
            ],
        },
        "evidence_kind": "web",
        "warnings": [],
        "truncated": False,
    }

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="Candidate found.",
                tool_events=[_event(payload)],
            )

    state = await run_supply_chain_workflow(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=False,
            cached_mode=False,
        ),
        steps=[
            SupplyChainProductResolverStep(),
            SupplyChainRequirementDecomposerStep(
                llm_client_factory=lambda _config: None,
            ),
            SupplyChainSupplierDiscoveryStep(
                search_router=EmptyRouter(),
                llm_client_factory=lambda _config: None,
                llm_runtime_factory=Runtime,
                llm_shadow_mode=True,
            ),
        ],
    )

    assert state.llm_tool_traces
    assert any(
        candidate.supplier_name == "NVIDIA"
        and candidate.relation_type == "supplied_by"
        and candidate.evidence_ids
        for candidate in state.llm_supplier_candidates
    )
    assert any(row.url == "https://www.reuters.com/technology/nvidia-ai-gpus" for row in state.evidence)
    assert not any(edge.target_node_id == "company:nvidia" for edge in state.links)


def test_supply_chain_llm_catalog_excludes_write_tools() -> None:
    catalog = build_project_tool_catalog(scope="supply_chain")
    assert "web_search" in catalog.names
    assert "sec_fetch_filing" in catalog.names
    assert "graph_write" not in catalog.names
    assert all(tool.risk_level != "write_gated" for tool in catalog.project_tools)
