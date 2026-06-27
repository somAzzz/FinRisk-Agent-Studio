"""v18 observability tests for supply-chain runs."""

from __future__ import annotations

from src.supply_chain.models import SupplyChainExploreRequest
from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
from src.supply_chain.steps.requirement_decomposer import (
    SupplyChainRequirementDecomposerStep,
)
from src.supply_chain.steps.supplier_discovery import SupplyChainSupplierDiscoveryStep
from src.supply_chain.workflow import run_supply_chain_workflow
from src.tools.providers.base import SearchResponse, SearchResult
from src.workflows.state import utcnow


class StubRouter:
    def search(self, query, intent="general", max_results=5):
        return SearchResponse(
            provider="stub",
            query=query,
            retrieved_at=utcnow(),
            results=[
                SearchResult(
                    title="NVIDIA supplies AI data center GPUs",
                    url="https://www.reuters.com/example",
                    snippet="NVIDIA GPUs power AI workloads.",
                    rank=1,
                )
            ],
        )


async def test_real_mode_records_trace_and_provider_calls() -> None:
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
                search_router=StubRouter(),
                llm_client_factory=lambda _config: None,
            ),
        ],
    )
    assert state.trace
    assert all(event.duration_ms is not None for event in state.trace)
    supplier_event = next(
        event for event in state.trace if event.step_name == "supplier_discovery"
    )
    assert supplier_event.input_summary["node_count"] > 0
    assert supplier_event.output_summary["evidence_count"] > 0
    assert supplier_event.provider_calls
    search_call = next(
        call for call in supplier_event.provider_calls if call.operation == "search"
    )
    assert search_call.provider == "stub"
    assert search_call.status == "success"
