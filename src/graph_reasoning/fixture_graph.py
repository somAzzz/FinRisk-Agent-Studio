"""Fixture graph for the v16 path retriever.

The fixture is intentionally small but rich enough for the demo
workflow: Apple → TSMC → Taiwan Strait risk, plus a couple of
"policy transmission" paths. The retriever uses it as the default
backend so the demo runs offline.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.graph_reasoning.models import (
    GraphEdge,
    GraphEdgeMetadata,
    GraphNode,
)

# Node ids are stable so the same fixture produces the same path
# ids across runs.
NODES: list[GraphNode] = [
    GraphNode(node_id="company:AAPL", node_type="Company", label="Apple Inc."),
    GraphNode(node_id="ticker:AAPL", node_type="Ticker", label="AAPL"),
    GraphNode(node_id="supplier:TSMC", node_type="Supplier", label="TSMC"),
    GraphNode(node_id="region:Taiwan", node_type="Region", label="Taiwan"),
    GraphNode(node_id="policy:tariff", node_type="Policy", label="US Tariff Regime"),
    GraphNode(node_id="risk:supply-asia", node_type="Risk", label="Asia supply chain"),
    GraphNode(node_id="risk:tariff", node_type="Risk", label="Tariff exposure"),
    GraphNode(node_id="event:taiwan-strait", node_type="Event", label="Taiwan Strait tension"),
    GraphNode(node_id="factor:macro", node_type="MacroFactor", label="Macro headwinds"),
]


def _e(
    src: str,
    dst: str,
    type_: str,
    evidence_ids: Iterable[str] = (),
    confidence: float = 0.7,
) -> GraphEdge:
    return GraphEdge(
        source_node_id=src,
        target_node_id=dst,
        edge_type=type_,
        metadata=GraphEdgeMetadata(
            source="fixture",
            evidence_ids=list(evidence_ids),
            confidence=confidence,
        ),
    )


EDGES: list[GraphEdge] = [
    _e("company:AAPL", "ticker:AAPL", "ISSUES"),
    _e("company:AAPL", "supplier:TSMC", "DEPENDS_ON", confidence=0.9),
    _e("supplier:TSMC", "region:Taiwan", "LOCATED_IN", confidence=0.95),
    _e("region:Taiwan", "event:taiwan-strait", "EXPOSED_TO", confidence=0.6),
    _e("company:AAPL", "policy:tariff", "EXPOSED_TO", confidence=0.85),
    _e("policy:tariff", "risk:tariff", "AFFECTS", confidence=0.7),
    _e("region:Taiwan", "risk:supply-asia", "AFFECTS", confidence=0.6),
    _e("factor:macro", "risk:tariff", "EXPOSED_TO", confidence=0.5),
]


__all__ = ["EDGES", "NODES"]
