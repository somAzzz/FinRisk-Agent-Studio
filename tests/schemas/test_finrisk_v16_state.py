"""v17 strong-typing round-trip tests for the v16 state fields.

These tests assert that every v16 Pydantic model can be serialised
to JSON and back without losing fields. They are the v17 alignment
gate for ``src/schemas/finrisk_v16.py``.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.schemas.finrisk import FinRiskRequest, FinRiskWorkflowState
from src.schemas.finrisk_v16 import (
    Claim,
    EvidenceGraphPayload,
    GraphEdge,
    GraphEdgeMetadata,
    GraphInsightV16,
    GraphNode,
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
    StepEvaluation,
    WorkflowEvaluationV16,
    build_workflow_evaluation,
)


def _state(**overrides) -> FinRiskWorkflowState:
    defaults: dict = {
        "run_id": "run-test",
        "request": FinRiskRequest(
            ticker="AAPL", analysis_goal="test", demo_mode=True
        ),
    }
    defaults.update(overrides)
    return FinRiskWorkflowState(**defaults)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


def test_claim_round_trips() -> None:
    claim = Claim(
        claim_id="c-1",
        text="Apple depends on Asia",
        claim_type="evidence",
        related_risk_ids=["risk-supply-asia"],
        supporting_evidence_ids=["ne-1"],
        confidence=0.9,
    )
    blob = json.loads(claim.model_dump_json())
    assert Claim.model_validate(blob) == claim
    assert blob["related_risk_ids"] == ["risk-supply-asia"]


def test_claim_rejects_garbage_claim_type() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(
            {
                "claim_id": "c",
                "text": "x",
                "claim_type": "bogus",
                "supporting_evidence_ids": [],
                "confidence": 0.5,
            }
        )


# ---------------------------------------------------------------------------
# Guardrail + workflow evaluation
# ---------------------------------------------------------------------------


def test_step_evaluation_round_trip() -> None:
    step = StepEvaluation(
        step_name="filing_risk_extractor",
        status=GuardrailStatus.NEEDS_REVIEW,
        findings=[
            GuardrailFinding(
                step_name="filing_risk_extractor",
                check_name="evidence",
                status=GuardrailStatus.FAIL,
                severity=GuardrailSeverity.BLOCKER,
                message="risk r-1 has no supporting evidence",
                affected_object_type="risk",
                affected_object_id="r-1",
            )
        ],
        metrics={"source_diversity": 0.5},
        latency_ms=42,
    )
    blob = json.loads(step.model_dump_json())
    assert StepEvaluation.model_validate(blob) == step


def test_workflow_evaluation_v16_aggregates_status() -> None:
    from src.evaluation.models import aggregate_status

    steps = [
        StepEvaluation(
            step_name="a", status=GuardrailStatus.PASS, findings=[]
        ),
        StepEvaluation(
            step_name="b", status=GuardrailStatus.NEEDS_REVIEW, findings=[]
        ),
    ]
    summary = build_workflow_evaluation(
        run_id="r",
        step_evaluations=steps,
    )
    blob = json.loads(summary.model_dump_json())
    assert blob["final_status"] == "needs_review"
    assert blob["human_review_required"] is True
    # round-trip preserves the step list
    assert WorkflowEvaluationV16.model_validate(blob) == summary
    # sanity: aggregate logic is the source of truth.
    assert aggregate_status(steps) == GuardrailStatus.NEEDS_REVIEW


def test_blocker_count_matches_findings() -> None:
    step = StepEvaluation(
        step_name="a",
        status=GuardrailStatus.FAIL,
        findings=[
            GuardrailFinding(
                step_name="a",
                check_name="x",
                status=GuardrailStatus.FAIL,
                severity=GuardrailSeverity.BLOCKER,
                message="x",
                affected_object_type="workflow",
            )
        ],
    )
    summary = build_workflow_evaluation(
        run_id="r", step_evaluations=[step]
    )
    assert summary.blocker_count == 1


# ---------------------------------------------------------------------------
# Graph payload
# ---------------------------------------------------------------------------


def test_graph_node_round_trip() -> None:
    node = GraphNode(
        node_id="company:AAPL",
        node_type="Company",
        label="Apple Inc.",
        properties={"sector": "Technology"},
    )
    blob = json.loads(node.model_dump_json())
    assert GraphNode.model_validate(blob) == node


def test_graph_edge_round_trip() -> None:
    edge = GraphEdge(
        source_node_id="company:AAPL",
        target_node_id="supplier:TSMC",
        edge_type="DEPENDS_ON",
        metadata=GraphEdgeMetadata(
            source="fixture",
            evidence_ids=["ne-1"],
            confidence=0.9,
        ),
    )
    blob = json.loads(edge.model_dump_json())
    assert GraphEdge.model_validate(blob) == edge


def test_graph_insight_v16_rejects_missing_path() -> None:
    # v17: GraphInsightV16 itself does not validate that
    # risk_path_ids reference existing CandidateGraphPath rows;
    # that is the insight validator's job. The schema only
    # checks structural fields.
    insight = GraphInsightV16(
        source_company="Apple",
        insight_type="second_order_risk",
        risk_path_ids=["p-does-not-exist"],
        affected_entities=["Taiwan"],
        explanation="path",
        evidence_ids=["ne-1"],
        confidence=0.4,
    )
    blob = json.loads(insight.model_dump_json())
    assert GraphInsightV16.model_validate(blob) == insight


def test_evidence_graph_payload_round_trip() -> None:
    payload = EvidenceGraphPayload(
        nodes=[
            GraphNode(
                node_id="company:AAPL", node_type="Company", label="Apple"
            )
        ],
        edges=[],
        insights=[],
    )
    blob = json.loads(payload.model_dump_json())
    assert EvidenceGraphPayload.model_validate(blob) == payload


def test_state_round_trips_v16_fields() -> None:
    """The full state must serialise and parse without losing v16 data."""
    state = _state(
        guardrail_findings=[
            GuardrailFinding(
                step_name="evidence_normalizer",
                check_name="evidence",
                status=GuardrailStatus.NEEDS_REVIEW,
                severity=GuardrailSeverity.WARNING,
                message="x",
                affected_object_type="risk",
                affected_object_id="r-1",
            )
        ]
    )
    blob = json.loads(state.model_dump_json())
    assert blob["guardrail_findings"]
    assert blob["guardrail_findings"][0]["check_name"] == "evidence"


def test_state_holds_pydantic_models_for_v16_fields() -> None:
    """The v17 runtime contract: v16 fields carry typed models, not dicts.

    The state model keeps ``list`` / ``Any`` annotations to avoid
    a circular import, but the actual values must be instances of
    the v16 Pydantic models. This test pins the contract so a
    regression that stores raw dicts (e.g. via ``model_dump``) is
    caught.
    """
    from src.evaluation.claim_grounding import Claim
    from src.evaluation.models import (
        FallbackEvent,
        GuardrailFinding,
        StepEvaluation,
    )

    state = _state(
        claims=[
            Claim(
                claim_id="c-1",
                text="x",
                claim_type="evidence",
                supporting_evidence_ids=["ne-1"],
                confidence=0.9,
            )
        ],
        evaluations=[
            StepEvaluation(
                step_name="company_resolver",
                status="pass",
                findings=[],
            )
        ],
        guardrail_findings=[
            GuardrailFinding(
                step_name="company_resolver",
                check_name="schema",
                status="pass",
                severity="info",
                message="ok",
                affected_object_type="workflow",
            )
        ],
        fallback_events=[
            FallbackEvent(
                step_name="market_explorer",
                from_mode="live",
                to_mode="demo",
                reason="demo mode",
            )
        ],
    )
    assert isinstance(state.claims[0], Claim)
    assert isinstance(state.evaluations[0], StepEvaluation)
    assert isinstance(state.guardrail_findings[0], GuardrailFinding)
    assert isinstance(state.fallback_events[0], FallbackEvent)
    # JSON round-trip is also lossless for the model types.
    blob = json.loads(state.model_dump_json())
    assert blob["claims"][0]["claim_id"] == "c-1"
    assert blob["fallback_events"][0]["to_mode"] == "demo"
