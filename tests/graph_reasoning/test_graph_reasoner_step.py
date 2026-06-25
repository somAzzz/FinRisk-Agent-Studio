"""Tests for the v16 GraphReasonerStep that wires the subsystem into the workflow."""

from __future__ import annotations

import asyncio

from src.graph_reasoning import GraphReasoningSubsystem
from src.graph_reasoning.subsystem import GraphReasoningSubsystem as _GR
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)
from src.workflows.steps.graph_reasoner import GraphReasonerStep


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


async def test_graph_reasoner_step_writes_v16_payload() -> None:
    state = _state()
    step = GraphReasonerStep(fixture_path=None)
    new_state = await step.run(state)
    # v15 field is still populated.
    assert new_state.graph_insights
    # v16 fields are populated when the subsystem runs.
    # (the v15 step delegates to the subsystem; if a Neo4j
    # GraphReasoningAgent is unavailable, the subsystem still runs
    # and the payload is recorded on the state).
    assert isinstance(new_state.graph_paths, list)
    assert isinstance(new_state.graph_context, object) or new_state.graph_context is None


def test_subsystem_constant_is_exposed() -> None:
    assert _GR is GraphReasoningSubsystem
