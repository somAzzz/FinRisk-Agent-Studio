"""Tests for v19 memory adapters."""

from __future__ import annotations

from src.memory.adapters import (
    memory_item_from_evidence,
    memory_item_from_supply_chain_edge,
    memory_item_from_supply_chain_evidence,
)
from src.schemas.evidence import Evidence
from src.supply_chain.models import NormalizedSupplyChainEvidence, SupplyChainEdge
from src.workflows.state import utcnow


def test_evidence_adapter_maps_sec_filing_to_filing_memory() -> None:
    """Canonical Evidence can be converted into active filing memory."""
    evidence = Evidence(
        evidence_id="ev-1",
        source_type="sec_filing",
        source_id="10-K",
        title="AAPL 10-K",
        url="https://sec.gov/example",
        quote="The company depends on third-party suppliers.",
        retrieved_at=utcnow(),
        confidence=0.9,
        metadata={"entities": ["Apple"], "tickers": ["AAPL"], "products": ["iPhone"]},
    )

    item = memory_item_from_evidence(evidence, run_id="run-1")

    assert item.memory_id == "mem:evidence:ev-1"
    assert item.source_type == "filing"
    assert item.status == "active"
    assert item.entities == ["Apple"]
    assert item.provenance["run_id"] == "run-1"


def test_evidence_adapter_maps_web_to_candidate_memory() -> None:
    """Web evidence defaults to candidate memory until validated."""
    evidence = Evidence(
        evidence_id="ev-web",
        source_type="web",
        source_id="search",
        url="https://example.com",
        quote="NVIDIA supplies AI accelerators.",
        retrieved_at=utcnow(),
        confidence=0.7,
    )

    item = memory_item_from_evidence(evidence)

    assert item.source_type == "web"
    assert item.status == "candidate"


def test_supply_chain_evidence_adapter_preserves_summary_and_source() -> None:
    """v18 NormalizedSupplyChainEvidence converts into MemoryItem."""
    evidence = NormalizedSupplyChainEvidence(
        evidence_id="sc-ev-1",
        source_type="company",
        source_name="Microsoft",
        url="https://example.com/azure",
        title="Azure infrastructure",
        quote="Azure provides infrastructure for AI services.",
        summary="Azure infrastructure evidence.",
        retrieved_at=utcnow(),
        confidence=0.85,
    )

    item = memory_item_from_supply_chain_evidence(evidence, run_id="run-2")

    assert item.memory_id == "mem:supply-evidence:sc-ev-1"
    assert item.source_type == "company"
    assert item.status == "active"
    assert item.summary == "Azure infrastructure evidence."


def test_supply_chain_edge_adapter_creates_active_graph_edge_memory() -> None:
    """Confirmed supply-chain edges become active graph-edge memory."""
    edge = SupplyChainEdge(
        edge_id="edge-gpu-nvidia",
        source_node_id="component:gpu",
        target_node_id="company:nvidia",
        relation_type="supplied_by",
        value=0.9,
        confidence=0.9,
        evidence_ids=["sc-ev-1"],
    )

    item = memory_item_from_supply_chain_edge(edge, run_id="run-3")

    assert item.memory_type == "graph_edge"
    assert item.claim_type == "evidence"
    assert item.status == "active"
    assert item.provenance["evidence_ids"] == ["sc-ev-1"]


def test_supply_chain_edge_adapter_creates_candidate_hypothesis_memory() -> None:
    """Hypothesized edges are represented as candidate hypothesis memory."""
    edge = SupplyChainEdge(
        edge_id="edge-cpu-intel",
        source_node_id="component:cpu",
        target_node_id="company:intel",
        relation_type="hypothesized",
        value=0.5,
        confidence=0.45,
        metadata={"reason": "needs confirmation"},
    )

    item = memory_item_from_supply_chain_edge(edge)

    assert item.memory_type == "graph_edge"
    assert item.claim_type == "hypothesis"
    assert item.status == "candidate"
