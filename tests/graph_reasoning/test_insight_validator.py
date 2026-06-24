"""Tests for the v16 insight validator."""

from __future__ import annotations

from src.evaluation.models import GuardrailSeverity
from src.graph_reasoning import (
    FIXTURE_EDGES,
    FIXTURE_NODES,
    GraphReasoningSubsystem,
    build_graph_context,
    interpret_paths,
    rank_paths,
    retrieve_candidate_paths,
    validate_all,
)
from src.graph_reasoning.models import GraphInsightV16
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


def _state() -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="supply chain", demo_mode=True),
        normalized_evidence=[
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
        ],
    )


def test_insight_validator_blocks_missing_path() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    bad = GraphInsightV16(
        source_company="Apple Inc.",
        insight_type="second_order_risk",
        risk_path_ids=["p-does-not-exist"],
        affected_entities=["Taiwan Strait risk"],
        explanation="bogus",
        evidence_ids=["ne-1"],
        confidence=0.4,
    )
    findings = validate_all([bad], state, ranked)
    assert any(f.severity == GuardrailSeverity.BLOCKER for f in findings)


def test_insight_validator_blocks_fabricated_affected_entity() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    insights = interpret_paths(ranked, state, top_k=1)
    assert insights
    insights[0].affected_entities.append("Zeta Reticuli")
    findings = validate_all(insights, state, ranked)
    assert any(f.severity == GuardrailSeverity.BLOCKER for f in findings)


def test_insight_validator_downgrades_confidence_too_high() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    insights = interpret_paths(ranked, state, top_k=1)
    insights[0].confidence = 0.99
    findings = validate_all(insights, state, ranked)
    assert any(f.severity == GuardrailSeverity.WARNING for f in findings)
    assert insights[0].confidence < 0.99


def test_subsystem_produces_payload_with_nodes_paths_insights() -> None:
    state = _state()
    payload = GraphReasoningSubsystem().run(state)
    assert payload.paths
    assert payload.insights
    assert payload.nodes
    assert payload.edges
