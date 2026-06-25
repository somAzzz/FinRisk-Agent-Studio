"""v18 Step 3: supplier discovery.

Demo/cached mode keeps using the fixture edges produced by the
requirement decomposer. Real mode calls the existing
``SearchRouter`` and converts high-quality snippets into
evidence-backed supplier nodes and edges.
"""

from __future__ import annotations

import time
from typing import Any

from src.supply_chain.evidence import build_evidence_from_search
from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    ProviderCall,
    SupplyChainEdge,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep

KNOWN_SUPPLIERS: dict[str, tuple[str, str | None]] = {
    "microsoft": ("Microsoft", "MSFT"),
    "azure": ("Microsoft", "MSFT"),
    "oracle": ("Oracle", "ORCL"),
    "coreweave": ("CoreWeave", None),
    "nvidia": ("NVIDIA", "NVDA"),
    "amd": ("AMD", "AMD"),
    "intel": ("Intel", "INTC"),
    "sk hynix": ("SK hynix", None),
    "samsung": ("Samsung", None),
    "micron": ("Micron", "MU"),
    "broadcom": ("Broadcom", "AVGO"),
    "arista": ("Arista Networks", "ANET"),
    "cisco": ("Cisco", "CSCO"),
    "marvell": ("Marvell", "MRVL"),
    "tsmc": ("TSMC", "TSM"),
    "asml": ("ASML", "ASML"),
    "synopsys": ("Synopsys", "SNPS"),
    "cadence": ("Cadence", "CDNS"),
}


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _supplier_from_text(text: str) -> tuple[str, str | None] | None:
    lowered = text.lower()
    for needle, supplier in KNOWN_SUPPLIERS.items():
        if needle in lowered:
            return supplier
    return None


def _intent_for_requirement(label: str) -> str:
    lowered = label.lower()
    if "cloud" in lowered:
        return "cloud_dependency"
    if "power" in lowered or "energy" in lowered:
        return "datacenter_power"
    if any(token in lowered for token in ("gpu", "cpu", "hbm", "semiconductor")):
        return "semiconductor_supply_chain"
    return "component_supplier"


class SupplyChainSupplierDiscoveryStep(SupplyChainStep):
    """Attach supplier edges to each requirement node.

    In demo mode the step is a no-op: the supplier edges are
    already part of the fixture consumed by the requirement
    decomposer. In real mode, the step uses SearchRouter with
    deterministic extraction rules. This keeps the production path
    evidence-backed while avoiding LLM-only assertions.
    """

    name = "supplier_discovery"

    def __init__(self, *, search_router: Any | None = None, max_results: int = 3) -> None:
        super().__init__()
        self._search_router = search_router
        self._max_results = max_results

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if state.request.demo_mode or state.request.cached_mode:
            return state
        router = self._search_router
        if router is None:
            try:
                from src.tools.search_router import SearchRouter

                router = SearchRouter()
            except Exception as exc:
                state.fallback_events.append(
                    f"supplier_discovery:search router unavailable: {exc}"
                )
                return state
        requirement_nodes = [
            node for node in state.nodes
            if node.node_type in {"component", "service", "energy", "infrastructure"}
        ]
        for requirement in requirement_nodes[: state.request.max_suppliers_per_node * 2]:
            intent = _intent_for_requirement(requirement.label)
            query = (
                f"{state.request.company_name or state.request.ticker} "
                f"{state.request.product_name} {requirement.label}"
            )
            try:
                started = time.perf_counter()
                response = router.search(
                    query=query,
                    intent=intent,
                    max_results=self._max_results,
                )
                self._record_provider_call(
                    state,
                    ProviderCall(
                        provider=getattr(response, "provider", "search"),
                        operation="search",
                        status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    ),
                )
            except Exception as exc:
                self._record_provider_call(
                    state,
                    ProviderCall(
                        provider=router.__class__.__name__,
                        operation="search",
                        status="failed",
                        latency_ms=0,
                        error=str(exc),
                    ),
                )
                state.fallback_events.append(
                    f"supplier_discovery:search failed for {requirement.node_id}: {exc}"
                )
                continue
            if not response.results:
                state.warnings.append(
                    f"supplier_discovery:no search results for {requirement.label}"
                )
                continue
            self._add_supplier_edges(state, requirement, response)
        if not any(edge.relation_type == "supplied_by" for edge in state.links):
            state.fallback_events.append(
                "supplier_discovery:no confirmed suppliers discovered from search"
            )
        return state

    def _add_supplier_edges(
        self,
        state: SupplyChainExploreState,
        requirement: SupplyChainNode,
        response: Any,
    ) -> None:
        existing_nodes = {node.node_id for node in state.nodes}
        existing_edges = {edge.edge_id for edge in state.links}
        existing_evidence = {ev.evidence_id for ev in state.evidence}
        added = 0
        for result in response.results:
            text = f"{result.title} {result.snippet} {result.url}"
            supplier = _supplier_from_text(text)
            if supplier is None:
                continue
            supplier_name, ticker = supplier
            evidence_dict = build_evidence_from_search(
                {
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.snippet,
                },
                query=response.query,
            )
            is_confirmed = bool(evidence_dict.pop("is_confirmed", False))
            evidence = NormalizedSupplyChainEvidence.model_validate(evidence_dict)
            if evidence.evidence_id not in existing_evidence:
                state.evidence.append(evidence)
                existing_evidence.add(evidence.evidence_id)
            supplier_id = f"company:{_slug(supplier_name)}"
            if supplier_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=supplier_id,
                        node_type="company",
                        label=supplier_name,
                        normalized_name=_slug(supplier_name),
                        ticker=ticker,
                        depth=requirement.depth + 1,
                        parent_node_id=requirement.node_id,
                        confidence=evidence.confidence,
                        evidence_ids=[evidence.evidence_id],
                        metadata={"method": "search_supplier_discovery"},
                    )
                )
                existing_nodes.add(supplier_id)
            relation_type = "supplied_by" if is_confirmed else "hypothesized"
            edge_id = f"sc-edge:{requirement.node_id}:{supplier_id}:supplied_by"
            if edge_id in existing_edges:
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=requirement.node_id,
                    target_node_id=supplier_id,
                    relation_type=relation_type,
                    value=0.6,
                    confidence=evidence.confidence,
                    evidence_ids=[evidence.evidence_id] if is_confirmed else [],
                    metadata={
                        "query": response.query,
                        "provider": response.provider,
                        "method": "search_supplier_discovery",
                        **({} if is_confirmed else {"reason": "search result lacked URL or quote"}),
                    },
                )
            )
            existing_edges.add(edge_id)
            added += 1
            if added >= state.request.max_suppliers_per_node:
                break

    @staticmethod
    def _record_provider_call(
        state: SupplyChainExploreState,
        call: ProviderCall,
    ) -> None:
        if not state.trace:
            return
        state.trace[-1].provider_calls.append(call)


__all__ = ["SupplyChainSupplierDiscoveryStep"]
