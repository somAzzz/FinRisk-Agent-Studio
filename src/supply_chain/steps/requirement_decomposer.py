"""v18 Step 2: requirement decomposer."""

from __future__ import annotations

from typing import Any

from src.supply_chain.fixtures import build_default_fixture
from src.supply_chain.llm import (
    build_supply_chain_llm_client,
    complete_json_with_trace,
)
from src.supply_chain.models import (
    ProviderCall,
    SupplyChainEdge,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep

_GENERIC_REQUIREMENTS: tuple[tuple[str, str, str, float], ...] = (
    ("service:cloud-compute", "service", "Cloud compute", 1.0),
    ("component:gpu-accelerator", "component", "GPU accelerator", 0.9),
    ("component:cpu", "component", "CPU/server platform", 0.55),
    ("component:hbm-memory", "component", "HBM memory", 0.75),
    ("component:networking", "component", "Networking", 0.45),
    ("energy:datacenter-power", "energy", "Data center power", 0.75),
)


def _fixtures_by_product() -> dict[str, dict[str, Any]]:
    """Map the demo product to its requirements subgraph."""
    fixture = build_default_fixture()
    return {fixture["request"]["product_name"].lower(): fixture}


class SupplyChainRequirementDecomposerStep(SupplyChainStep):
    """Decompose a product into upstream requirements.

    Demo/cached runs keep using the deterministic fixture. Real runs
    first ask the configured LLM for a structured decomposition, then
    fall back to a small ruleset if the model is unavailable.
    """

    name = "requirement_decomposer"

    def __init__(self, *, llm_client_factory: Any | None = None) -> None:
        super().__init__()
        self._llm_client_factory = llm_client_factory

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        product_key = state.request.product_name.strip().lower()
        fixtures = _fixtures_by_product()
        if (state.request.demo_mode or state.request.cached_mode) and product_key not in fixtures:
            # Unknown product: record a warning so the evaluator
            # can downgrade the run to needs_review.
            state.warnings.append(
                f"no demo fixture for product {state.request.product_name!r}"
            )
            return state
        if not (state.request.demo_mode or state.request.cached_mode):
            if not self._add_llm_requirements(state):
                state.fallback_events.append(
                    "requirement_decomposer:llm unavailable; used rule fallback"
                )
                self._add_rule_requirements(state)
            return state
        fixture = fixtures[product_key]
        # Merge nodes / links / evidence from the fixture into the
        # state. The product resolver already added the root
        # nodes; skip duplicates.
        existing_ids = {n.node_id for n in state.nodes}
        for raw in fixture["nodes"]:
            if raw["node_id"] in existing_ids:
                continue
            state.nodes.append(SupplyChainNode.model_validate(raw))
        existing_edges = {(e.source_node_id, e.target_node_id) for e in state.links}
        for raw in fixture["links"]:
            key = (raw["source_node_id"], raw["target_node_id"])
            if key in existing_edges:
                continue
            state.links.append(SupplyChainEdge.model_validate(raw))
        return state

    def _add_llm_requirements(self, state: SupplyChainExploreState) -> bool:
        client = self._build_llm_client(state)
        provider = state.request.llm_config.provider
        if client is None:
            self._record_provider_call(
                state,
                ProviderCall(
                    provider=provider,
                    operation="decompose_requirements",
                    status="failed",
                    latency_ms=0,
                    error="LLM client unavailable",
                ),
            )
            return False
        payload, call = complete_json_with_trace(
            client=client,
            provider=provider,
            operation="decompose_requirements",
            system=(
                "You are a supply-chain analyst. Return compact JSON only. "
                "Do not include markdown or commentary."
            ),
            prompt=_requirement_prompt(state),
            max_tokens=1200,
            temperature=0.1,
        )
        self._record_provider_call(state, call)
        requirements = _coerce_requirements(payload)
        if not requirements:
            return False
        product_id = f"product:{state.request.product_name.strip().lower().replace(' ', '-')}"
        existing_nodes = {n.node_id for n in state.nodes}
        existing_edges = {e.edge_id for e in state.links}
        added = 0
        for index, item in enumerate(requirements[:10]):
            label = item["label"]
            node_type = item["node_type"]
            node_id = f"{node_type}:{_slug(label)}"
            confidence = item["confidence"]
            importance = item["importance"]
            if node_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=node_id,
                        node_type=node_type,  # type: ignore[arg-type]
                        label=label,
                        normalized_name=label.lower(),
                        depth=1,
                        parent_node_id=product_id,
                        confidence=confidence,
                        metadata={
                            "method": "llm_requirement_decomposer",
                            "provider": provider,
                            **({"reason": item["reason"]} if item.get("reason") else {}),
                        },
                    )
                )
                existing_nodes.add(node_id)
            edge_id = f"sc-edge:{product_id}:{node_id}:requires"
            if edge_id in existing_edges:
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=product_id,
                    target_node_id=node_id,
                    relation_type="hypothesized",
                    value=importance,
                    confidence=confidence,
                    evidence_ids=[],
                    metadata={
                        "method": "llm_requirement_decomposer",
                        "provider": provider,
                        "reason": item.get("reason")
                        or "LLM product architecture decomposition",
                    },
                )
            )
            existing_edges.add(edge_id)
            added += 1
        if added:
            state.metrics["llm_requirement_count"] = (
                state.metrics.get("llm_requirement_count", 0) + added
            )
        return added > 0

    def _build_llm_client(self, state: SupplyChainExploreState) -> Any | None:
        if self._llm_client_factory is not None:
            return self._llm_client_factory(state.request.llm_config)
        return build_supply_chain_llm_client(state.request.llm_config)

    @staticmethod
    def _add_rule_requirements(state: SupplyChainExploreState) -> None:
        """Add rule-based upstream requirements for real/cached discovery.

        These edges are intentionally marked ``hypothesized`` because
        they are product-architecture inferences. Supplier discovery
        later upgrades company edges to confirmed when search evidence
        exists.
        """
        product_id = f"product:{state.request.product_name.strip().lower().replace(' ', '-')}"
        existing_nodes = {n.node_id for n in state.nodes}
        existing_edges = {e.edge_id for e in state.links}
        for node_id, node_type, label, value in _GENERIC_REQUIREMENTS:
            if node_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=node_id,
                        node_type=node_type,  # type: ignore[arg-type]
                        label=label,
                        normalized_name=label.lower(),
                        depth=1,
                        parent_node_id=product_id,
                        confidence=0.55,
                        metadata={"method": "rule_decomposer"},
                    )
                )
                existing_nodes.add(node_id)
            edge_id = f"sc-edge:{product_id}:{node_id}:requires"
            if edge_id in existing_edges:
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=product_id,
                    target_node_id=node_id,
                    relation_type="hypothesized",
                    value=value,
                    confidence=0.55,
                    evidence_ids=[],
                    metadata={
                        "reason": "rule-based product architecture decomposition",
                        "method": "rule_decomposer",
                    },
                )
            )
            existing_edges.add(edge_id)

    @staticmethod
    def _record_provider_call(
        state: SupplyChainExploreState,
        call: ProviderCall,
    ) -> None:
        if not state.trace:
            return
        state.trace[-1].provider_calls.append(call)


def _requirement_prompt(state: SupplyChainExploreState) -> str:
    company = state.request.company_name or state.request.ticker or "the company"
    regions = ", ".join(state.request.focus_regions) or "global"
    return (
        "Decompose the product into upstream supply-chain requirements.\n"
        f"Company: {company}\n"
        f"Product: {state.request.product_name}\n"
        f"Focus regions: {regions}\n"
        "Return JSON with this exact shape:\n"
        '{"requirements":[{"label":"GPU accelerator","node_type":"component",'
        '"importance":0.9,"confidence":0.75,"reason":"why it matters"}]}\n'
        "Allowed node_type values: component, service, infrastructure, energy, "
        "commodity, region, unknown. Return 4 to 8 concrete requirements."
    )


def _coerce_requirements(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("requirements") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    allowed = {
        "component",
        "service",
        "infrastructure",
        "energy",
        "commodity",
        "region",
        "unknown",
    }
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        node_type = str(row.get("node_type") or "unknown").strip().lower()
        if node_type not in allowed:
            node_type = "unknown"
        out.append(
            {
                "label": label[:120],
                "node_type": node_type,
                "importance": _clamp_float(row.get("importance"), default=0.6),
                "confidence": _clamp_float(row.get("confidence"), default=0.65),
                "reason": str(row.get("reason") or "").strip()[:240],
            }
        )
    return out


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


def _slug(value: str) -> str:
    return "-".join(value.strip().lower().split())


__all__ = ["SupplyChainRequirementDecomposerStep"]
