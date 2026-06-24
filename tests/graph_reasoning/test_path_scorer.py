"""Tests for the v16 path scorer."""

from __future__ import annotations

from src.graph_reasoning import (
    FIXTURE_EDGES,
    FIXTURE_NODES,
    build_graph_context,
    rank_paths,
    retrieve_candidate_paths,
    score_path,
)
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


def _state(*, with_evidence: bool = True) -> FinRiskWorkflowState:
    state = FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="supply chain", demo_mode=True),
    )
    if with_evidence:
        state.normalized_evidence = [
            NormalizedEvidence(
                evidence_id="ne-1",
                source_type="filing",
                source_name="10-K",
                source_url=None,
                quote="Apple relies on Asian suppliers",
                summary="Apple supply chain",
                related_risk_ids=[],
                credibility_score=0.9,
                collected_at=utcnow(),
            )
        ]
    return state


def test_score_path_returns_value_in_range() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    assert paths
    scored = score_path(paths[0], ctx, _state())
    assert 0.0 <= (scored.path_score or 0.0) <= 1.0
    assert "evidence_coverage" in scored.score_breakdown


def test_score_path_breaks_down_components() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    scored = score_path(paths[0], ctx, _state())
    expected_keys = {
        "evidence_coverage",
        "min_edge_confidence",
        "relevance",
        "source_quality",
        "novelty",
        "graph_centrality",
        "hub_penalty",
    }
    assert expected_keys.issubset(scored.score_breakdown)


def test_rank_paths_orders_by_score_desc() -> None:
    ctx = build_graph_context(_state())
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, _state())
    scores = [p.path_score or 0.0 for p in ranked]
    assert scores == sorted(scores, reverse=True)
