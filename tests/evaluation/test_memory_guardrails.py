"""Tests for v19 memory write and graph edge guardrails."""

from __future__ import annotations

from src.evaluation.memory_guardrails import GraphMemoryGuardrails, MemoryWriteGuardrails
from src.memory.models import MemoryItem
from src.supply_chain.models import SupplyChainEdge


def _item(
    *,
    source_type: str = "web",
    claim_type: str = "evidence",
    status: str = "active",
    memory_type: str = "evidence",
) -> MemoryItem:
    return MemoryItem(
        memory_type=memory_type,  # type: ignore[arg-type]
        text="NVIDIA supplies AI accelerators.",
        source_type=source_type,  # type: ignore[arg-type]
        source_url="https://example.com",
        credibility_score=0.8,
        freshness_score=0.9,
        confidence=0.8,
        claim_type=claim_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def test_web_active_memory_is_downgraded_to_candidate() -> None:
    """Untrusted web memory cannot be written directly as active."""
    decision = MemoryWriteGuardrails().validate(_item(source_type="web", status="active"))

    assert decision.allowed is True
    assert decision.target_status == "candidate"
    assert "untrusted_web_memory_downgraded_to_candidate" in decision.reasons


def test_llm_extracted_active_memory_is_downgraded() -> None:
    """LLM extracted memory requires candidate validation before active use."""
    item = _item(source_type="company", status="active")
    item = item.model_copy(update={"provenance": {"extracted_by": "llm"}})

    decision = MemoryWriteGuardrails().validate(item)

    assert decision.allowed is True
    assert decision.target_status == "candidate"
    assert "llm_extracted_memory_downgraded_to_candidate" in decision.reasons


def test_domain_prior_cannot_be_written_as_evidence() -> None:
    """Domain priors are not evidence."""
    decision = MemoryWriteGuardrails().validate(
        _item(source_type="domain_prior", claim_type="evidence", memory_type="domain_prior")
    )

    assert decision.allowed is False
    assert decision.reasons == ["domain_prior_cannot_be_evidence"]


def test_graph_guardrail_allows_confirmed_edge_with_evidence() -> None:
    """Confirmed graph edges with evidence can be written as active memory."""
    edge = SupplyChainEdge(
        edge_id="edge-1",
        source_node_id="component:gpu",
        target_node_id="company:nvidia",
        relation_type="supplied_by",
        value=0.8,
        confidence=0.8,
        evidence_ids=["ev-1"],
    )

    decision = GraphMemoryGuardrails().validate_edge(edge)

    assert decision.allowed is True
    assert decision.target_status == "active"


def test_graph_guardrail_blocks_confirmed_edge_without_evidence() -> None:
    """A malformed confirmed edge without evidence is blocked."""
    edge = SupplyChainEdge.model_construct(
        edge_id="edge-1",
        source_node_id="component:gpu",
        target_node_id="company:nvidia",
        relation_type="supplied_by",
        value=0.8,
        value_meaning="importance",
        confidence=0.8,
        evidence_ids=[],
        metadata={},
    )

    decision = GraphMemoryGuardrails().validate_edge(edge)

    assert decision.allowed is False
    assert decision.reasons == ["confirmed_edge_missing_evidence"]


def test_graph_guardrail_downgrades_hypothesis_edge() -> None:
    """Hypothesized graph edges are candidate memory."""
    edge = SupplyChainEdge(
        edge_id="edge-2",
        source_node_id="component:cpu",
        target_node_id="company:intel",
        relation_type="hypothesized",
        value=0.5,
        confidence=0.4,
        metadata={"reason": "needs evidence"},
    )

    decision = GraphMemoryGuardrails().validate_edge(edge)

    assert decision.allowed is True
    assert decision.target_status == "candidate"
