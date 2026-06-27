"""v18 Step 6: node intelligence profile generation."""

from __future__ import annotations

import re
from typing import Any

from src.supply_chain.llm import (
    build_supply_chain_llm_client,
    complete_json_with_trace,
)
from src.supply_chain.models import (
    ProviderCall,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep

_MAX_PROFILED_NODES = 14


class SupplyChainNodeProfileStep(SupplyChainStep):
    """Attach concise structured profiles to graph nodes.

    Real runs ask the configured LLM for node-level intelligence. Demo,
    cached, and failed LLM paths use deterministic taxonomy fallbacks
    so tests remain stable and the frontend always has something useful
    to render.
    """

    name = "node_profile"

    def __init__(self, *, llm_client_factory: Any | None = None) -> None:
        super().__init__()
        self._llm_client_factory = llm_client_factory

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        targets = _profile_targets(state.nodes)
        if not targets:
            return state
        llm_profiles: dict[str, dict[str, Any]] = {}
        if not (state.request.demo_mode or state.request.cached_mode):
            llm_profiles = self._generate_llm_profiles(state, targets)
            if not llm_profiles:
                state.fallback_events.append(
                    "node_profile:llm unavailable; used taxonomy fallback"
                )
        target_ids = {target.node_id for target in targets}
        for node in state.nodes:
            if node.node_id not in target_ids:
                continue
            profile = llm_profiles.get(node.node_id) or _taxonomy_profile(node, state)
            node.metadata["profile"] = _coerce_profile(profile, node)
        return state

    def _generate_llm_profiles(
        self,
        state: SupplyChainExploreState,
        targets: list[SupplyChainNode],
    ) -> dict[str, dict[str, Any]]:
        client = self._build_llm_client(state)
        provider = state.request.llm_config.provider
        if client is None:
            self._record_provider_call(
                state,
                ProviderCall(
                    provider=provider,
                    operation="profile_supply_chain_nodes",
                    status="failed",
                    latency_ms=0,
                    error="LLM client unavailable",
                ),
            )
            return {}
        payload, call = complete_json_with_trace(
            client=client,
            provider=provider,
            operation="profile_supply_chain_nodes",
            system=(
                "You are a supply-chain analyst. Return compact JSON only. "
                "Do not include markdown or commentary."
            ),
            prompt=_profile_prompt(state, targets),
            max_tokens=1800,
            temperature=0.1,
        )
        self._record_provider_call(state, call)
        return _coerce_llm_profiles(payload)

    def _build_llm_client(self, state: SupplyChainExploreState) -> Any | None:
        if self._llm_client_factory is not None:
            return self._llm_client_factory(state.request.llm_config)
        return build_supply_chain_llm_client(state.request.llm_config)

    @staticmethod
    def _record_provider_call(
        state: SupplyChainExploreState,
        call: ProviderCall,
    ) -> None:
        if not state.trace:
            return
        state.trace[-1].provider_calls.append(call)


def _profile_targets(nodes: list[SupplyChainNode]) -> list[SupplyChainNode]:
    priority = {
        "commodity": 0,
        "infrastructure": 1,
        "energy": 2,
        "component": 3,
        "service": 4,
        "company": 5,
    }
    candidates = [
        node
        for node in nodes
        if node.node_type in priority and node.depth <= 3
    ]
    return sorted(
        candidates,
        key=lambda node: (
            priority.get(node.node_type, 9),
            node.depth,
            -node.confidence,
            node.label.lower(),
        ),
    )[:_MAX_PROFILED_NODES]


def _profile_prompt(
    state: SupplyChainExploreState,
    targets: list[SupplyChainNode],
) -> str:
    node_by_id = {node.node_id: node for node in state.nodes}
    children_by_parent: dict[str, list[str]] = {}
    for node in state.nodes:
        if node.parent_node_id:
            children_by_parent.setdefault(node.parent_node_id, []).append(node.label)
    evidence_by_id = {ev.evidence_id: ev for ev in state.evidence}
    rows = []
    for node in targets:
        parent = node_by_id.get(node.parent_node_id or "")
        evidence = [
            evidence_by_id[eid].summary
            for eid in node.evidence_ids
            if eid in evidence_by_id
        ][:2]
        rows.append(
            {
                "node_id": node.node_id,
                "label": node.label,
                "node_type": node.node_type,
                "parent": parent.label if parent else None,
                "children": children_by_parent.get(node.node_id, [])[:6],
                "evidence_summaries": evidence,
            }
        )
    return (
        "Create concise node intelligence cards for a product supply-chain graph.\n"
        f"Company: {state.request.company_name or state.request.ticker or 'unknown'}\n"
        f"Product: {state.request.product_name}\n"
        "For company nodes, describe operating scope and comparable suppliers. "
        "For commodity/material nodes, list involved minerals/materials. "
        "For infrastructure, energy, service, and component nodes, list system "
        "parts, applications, supplier categories, and risk factors.\n"
        "Return JSON with this exact shape:\n"
        '{"profiles":[{"node_id":"component:example","summary":"...",'
        '"key_items":["item"],"applications":["use"],"risk_factors":["risk"],'
        '"comparable_entities":["peer"],"confidence":0.75}]}\n'
        "Keep each list to 3-6 short items. Use plain business language.\n"
        f"Nodes: {rows}"
    )


def _coerce_llm_profiles(payload: Any) -> dict[str, dict[str, Any]]:
    rows = payload.get("profiles") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "").strip()
        if not node_id:
            continue
        profiles[node_id] = row
    return profiles


def _coerce_profile(profile: dict[str, Any], node: SupplyChainNode) -> dict[str, Any]:
    return {
        "summary": _string(profile.get("summary"))
        or f"{node.label} is a {node.node_type} dependency in this supply-chain graph.",
        "key_items": _string_list(profile.get("key_items")),
        "applications": _string_list(profile.get("applications")),
        "risk_factors": _string_list(profile.get("risk_factors")),
        "comparable_entities": _string_list(profile.get("comparable_entities")),
        "generated_by": _string(profile.get("generated_by"))
        or _string(profile.get("source"))
        or "llm",
        "confidence": _float(profile.get("confidence"), default=node.confidence),
    }


def _taxonomy_profile(
    node: SupplyChainNode,
    state: SupplyChainExploreState,
) -> dict[str, Any]:
    label_key = _normalise(node.label)
    graph_peers = _graph_peers(node, state.nodes)
    if "rare-earth" in label_key or "rare-earth-mineral" in label_key:
        return {
            "summary": (
                "Rare earth materials are upstream mineral inputs used in high-strength "
                "magnets, motors, power electronics, and specialized manufacturing."
            ),
            "key_items": [
                "Neodymium",
                "Praseodymium",
                "Dysprosium",
                "Terbium",
                "Rare earth oxides",
            ],
            "applications": [
                "Permanent magnets",
                "Electric motors",
                "Power equipment",
                "Advanced electronics",
            ],
            "risk_factors": [
                "Mining and separation concentration",
                "Export controls",
                "Long qualification cycles",
                "Limited substitution",
            ],
            "comparable_entities": graph_peers
            or ["Lithium", "Cobalt", "Gallium", "Graphite"],
            "generated_by": "taxonomy",
            "confidence": 0.72,
        }
    if "high-voltage" in label_key or (
        "electrical" in label_key and "system" in label_key
    ):
        return {
            "summary": (
                "High-voltage electrical systems connect large compute sites to grid "
                "power and distribute resilient power across substations, switchgear, "
                "transformers, UPS equipment, and protection systems."
            ),
            "key_items": [
                "Power transformers",
                "Switchgear",
                "Substations",
                "UPS systems",
                "Power distribution units",
            ],
            "applications": [
                "Data-center grid interconnect",
                "Load balancing",
                "Backup power continuity",
                "Facility electrical protection",
            ],
            "risk_factors": [
                "Transformer lead times",
                "Grid interconnection delays",
                "Copper and electrical steel constraints",
                "Certification and commissioning bottlenecks",
            ],
            "comparable_entities": graph_peers
            or ["Schneider Electric", "ABB", "Siemens Energy", "Eaton"],
            "generated_by": "taxonomy",
            "confidence": 0.74,
        }
    if node.node_type == "company":
        return _company_taxonomy_profile(node, graph_peers)
    if node.node_type == "commodity":
        return {
            "summary": (
                f"{node.label} represents a material input that may constrain cost, "
                "availability, qualification, or geopolitical exposure."
            ),
            "key_items": _children(node, state.nodes) or [node.label],
            "applications": ["Manufacturing input", "Critical component sourcing"],
            "risk_factors": [
                "Supplier concentration",
                "Price volatility",
                "Trade restrictions",
            ],
            "comparable_entities": graph_peers,
            "generated_by": "taxonomy",
            "confidence": max(0.55, node.confidence),
        }
    if node.node_type in {"component", "infrastructure", "energy", "service"}:
        return {
            "summary": (
                f"{node.label} is a {node.node_type} dependency for "
                f"{state.request.product_name}, with exposure driven by capacity, "
                "supplier concentration, evidence strength, and qualification cycles."
            ),
            "key_items": _children(node, state.nodes) or [node.label],
            "applications": ["Product delivery", "Operational resilience"],
            "risk_factors": [
                "Capacity constraints",
                "Vendor concentration",
                "Low evidence coverage",
            ],
            "comparable_entities": graph_peers,
            "generated_by": "taxonomy",
            "confidence": max(0.55, node.confidence),
        }
    return {
        "summary": f"{node.label} is a dependency candidate in this graph.",
        "key_items": _children(node, state.nodes),
        "applications": [],
        "risk_factors": ["Evidence may require review"],
        "comparable_entities": graph_peers,
        "generated_by": "taxonomy",
        "confidence": max(0.45, node.confidence),
    }


def _company_taxonomy_profile(
    node: SupplyChainNode,
    graph_peers: list[str],
) -> dict[str, Any]:
    known: dict[str, tuple[str, list[str]]] = {
        "sk-hynix": (
            "Memory semiconductor supplier focused on DRAM, NAND flash, and "
            "high-bandwidth memory used in AI accelerators.",
            ["Samsung Electronics", "Micron", "Kioxia", "Western Digital"],
        ),
        "samsung": (
            "Diversified electronics and semiconductor manufacturer with DRAM, "
            "NAND, HBM, foundry, display, and device businesses.",
            ["SK Hynix", "Micron", "TSMC", "Kioxia"],
        ),
        "micron": (
            "Memory manufacturer supplying DRAM, NAND, and HBM products for "
            "data center, client, automotive, and industrial markets.",
            ["SK Hynix", "Samsung Electronics", "Kioxia", "Western Digital"],
        ),
        "microsoft-azure": (
            "Cloud infrastructure platform providing compute, storage, networking, "
            "AI services, and managed data services.",
            ["Amazon Web Services", "Google Cloud", "Oracle Cloud", "CoreWeave"],
        ),
        "amazon-web-services": (
            "Cloud infrastructure platform providing compute, storage, networking, "
            "databases, AI services, and managed platforms.",
            ["Microsoft Azure", "Google Cloud", "Oracle Cloud", "CoreWeave"],
        ),
        "nvidia": (
            "Accelerated computing company supplying GPUs, AI accelerators, "
            "networking, and software platforms for data centers.",
            ["AMD", "Intel", "Broadcom", "Marvell"],
        ),
    }
    label_key = _normalise(node.label)
    summary, peers = known.get(
        label_key,
        (
            "Company node identified as a supplier, infrastructure provider, "
            "manufacturer, or dependency candidate in this supply-chain graph.",
            [],
        ),
    )
    return {
        "summary": summary,
        "key_items": [],
        "applications": ["Supply-chain dependency"],
        "risk_factors": ["Evidence strength and concentration require review"],
        "comparable_entities": _unique([*peers, *graph_peers], exclude=node.label),
        "generated_by": "taxonomy",
        "confidence": max(0.55, node.confidence),
    }


def _graph_peers(node: SupplyChainNode, nodes: list[SupplyChainNode]) -> list[str]:
    return _unique(
        [
            candidate.label
            for candidate in nodes
            if candidate.node_type == node.node_type
            and candidate.node_id != node.node_id
            and candidate.parent_node_id == node.parent_node_id
        ],
        exclude=node.label,
    )


def _children(node: SupplyChainNode, nodes: list[SupplyChainNode]) -> list[str]:
    return _unique(
        [candidate.label for candidate in nodes if candidate.parent_node_id == node.node_id]
    )[:6]


def _unique(values: list[str], *, exclude: str | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    excluded = _normalise(exclude or "")
    for value in values:
        key = _normalise(value)
        if not key or key == excluded or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out[:6]


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text[:100] for text in (_string(item) for item in value) if text][:6]


def _float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(1.0, max(0.0, parsed))


def _normalise(value: str) -> str:
    text = value.strip().lower().replace("&", " and ")
    text = re.sub(r"\b(?:electronics|corporation|corp|inc|ltd|co)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


__all__ = ["SupplyChainNodeProfileStep"]
