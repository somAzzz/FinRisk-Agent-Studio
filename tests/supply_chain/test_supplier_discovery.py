"""v18 tests for the search-extraction + supplier-discovery layer.

The tests use a stub search provider so the v18 unit tests run
offline. Spec 03's real-mode LLM + browser adapters are out of
scope for the v18 first demo and live in follow-up specs.
"""

from __future__ import annotations

from src.supply_chain.prompts import (
    INTENT_QUERY_TEMPLATES,
    render_query,
)
from src.tools.providers.base import SearchResponse, SearchResult
from src.workflows.state import utcnow


def test_intent_templates_have_required_keys() -> None:
    expected = {
        "product_supply_chain",
        "supplier_discovery",
        "component_supplier",
        "cloud_dependency",
        "datacenter_power",
        "semiconductor_supply_chain",
    }
    assert expected.issubset(INTENT_QUERY_TEMPLATES.keys())


def test_render_query_substitutes_q() -> None:
    out = render_query("product_supply_chain", "OpenAI ChatGPT")
    assert "OpenAI ChatGPT" in out
    assert "suppliers" in out


def test_render_query_unknown_intent_returns_raw_query() -> None:
    assert render_query("mystery", "Foo") == "Foo"


def test_search_results_with_no_url_are_not_confirmed() -> None:
    """A snippet with no URL is treated as a hypothesis edge."""
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "",
        "title": "Anonymous blog post",
        "snippet": "NVIDIA H100 powers AI workloads.",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["confidence"] <= 0.5
    assert evidence["is_confirmed"] is False


def test_search_results_with_no_quote_are_not_confirmed() -> None:
    """A snippet with no quote / summary is a hypothesis."""
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "https://www.reuters.com/example",
        "title": "Reuters example",
        "snippet": "",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["is_confirmed"] is False


def test_search_results_with_url_and_quote_are_confirmed() -> None:
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "https://www.reuters.com/example",
        "title": "Reuters example",
        "snippet": "NVIDIA H100 powers AI workloads.",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["is_confirmed"] is True
    assert evidence["confidence"] >= 0.5


class StubRouter:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query, intent="general", max_results=5):
        self.queries.append((query, intent, max_results))
        return SearchResponse(
            provider="stub",
            query=query,
            retrieved_at=utcnow(),
            results=self.results,
        )


async def test_real_supplier_discovery_creates_confirmed_edge() -> None:
    from src.supply_chain.models import SupplyChainExploreRequest
    from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
    from src.supply_chain.steps.requirement_decomposer import (
        SupplyChainRequirementDecomposerStep,
    )
    from src.supply_chain.steps.supplier_discovery import (
        SupplyChainSupplierDiscoveryStep,
    )
    from src.supply_chain.workflow import run_supply_chain_workflow

    router = StubRouter(
        [
            SearchResult(
                title="NVIDIA supplies H100 GPUs for AI data centers",
                url="https://www.reuters.com/example",
                snippet="NVIDIA H100 GPUs power AI training and inference workloads.",
                rank=1,
            )
        ]
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
            SupplyChainRequirementDecomposerStep(),
            SupplyChainSupplierDiscoveryStep(search_router=router),
        ],
    )
    assert router.queries
    node_ids = {node.node_id for node in state.nodes}
    assert "company:nvidia" in node_ids
    assert any(
        edge.target_node_id == "company:nvidia"
        and edge.relation_type == "supplied_by"
        and edge.evidence_ids
        for edge in state.links
    )


async def test_real_supplier_discovery_records_fallback_on_search_error() -> None:
    from src.supply_chain.models import SupplyChainExploreRequest
    from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
    from src.supply_chain.steps.requirement_decomposer import (
        SupplyChainRequirementDecomposerStep,
    )
    from src.supply_chain.steps.supplier_discovery import (
        SupplyChainSupplierDiscoveryStep,
    )
    from src.supply_chain.workflow import run_supply_chain_workflow

    class FailingRouter:
        def search(self, *args, **kwargs):
            raise RuntimeError("search down")

    state = await run_supply_chain_workflow(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=False,
            cached_mode=False,
        ),
        steps=[
            SupplyChainProductResolverStep(),
            SupplyChainRequirementDecomposerStep(),
            SupplyChainSupplierDiscoveryStep(search_router=FailingRouter()),
        ],
    )
    assert any("search failed" in event for event in state.fallback_events)
