"""Tests for the v18 supply-chain graph writer."""

from __future__ import annotations

from src.graph.supply_chain_writer import SupplyChainGraphWriter
from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    SupplyChainEdge,
    SupplyChainNode,
)
from src.workflows.state import utcnow


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, params: dict) -> list[dict]:
        self.calls.append((cypher, params))
        return []


def test_supply_chain_writer_merges_nodes_edges_and_evidence() -> None:
    client = FakeClient()
    writer = SupplyChainGraphWriter(client)
    evidence = NormalizedSupplyChainEvidence(
        evidence_id="sc:web:1",
        source_type="web",
        source_name="example.com",
        url="https://example.com",
        quote="NVIDIA supplies AI accelerators.",
        summary="NVIDIA supplies AI accelerators.",
        retrieved_at=utcnow(),
        confidence=0.8,
    )
    nodes = [
        SupplyChainNode(
            node_id="component:gpu",
            node_type="component",
            label="GPU",
            normalized_name="gpu",
            depth=1,
            confidence=0.8,
        ),
        SupplyChainNode(
            node_id="company:nvidia",
            node_type="company",
            label="NVIDIA",
            normalized_name="nvidia",
            ticker="NVDA",
            depth=2,
            confidence=0.9,
            evidence_ids=["sc:web:1"],
        ),
    ]
    edges = [
        SupplyChainEdge(
            edge_id="edge:gpu:nvidia",
            source_node_id="component:gpu",
            target_node_id="company:nvidia",
            relation_type="supplied_by",
            value=0.8,
            confidence=0.8,
            evidence_ids=["sc:web:1"],
        )
    ]
    writer.write_graph(nodes=nodes, edges=edges, evidence=[evidence])
    cypher = "\n".join(call[0] for call in client.calls)
    assert "MERGE (n:Component" in cypher
    assert "MERGE (n:Company" in cypher
    assert "MERGE (e:Evidence" in cypher
    assert "SUPPLIED_BY" in cypher
