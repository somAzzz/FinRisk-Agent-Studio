"""Tests for the v16 path retriever."""

from __future__ import annotations

from src.graph_reasoning import (
    FIXTURE_EDGES,
    FIXTURE_NODES,
    build_graph_context,
    retrieve_candidate_paths,
)
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
)


def _state() -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="supply chain", demo_mode=True),
    )


def test_retriever_returns_paths_from_company_node() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    assert paths
    # Every path must start at the company node.
    for p in paths:
        assert p.nodes[0].node_id == "company:AAPL"


def test_retriever_filters_low_confidence_edges() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(
        ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES, min_edge_confidence=1.01
    )
    # All fixture edges have confidence <= 0.95, so nothing survives.
    assert paths == []


def test_retriever_collects_unique_evidence_ids() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    # evidence_ids should be deduplicated per path.
    for p in paths:
        assert len(p.evidence_ids) == len(set(p.evidence_ids))
