"""v17 alignment tests for the quality-gated orchestrator.

The audit requires the v16 runner to use the runtime quality layer
as the *primary* mechanism for collecting guardrail findings — not
a post-hoc trace scan. These tests pin that contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.evaluation.engine import GuardrailEngine
from src.evaluation.validators import EvidenceValidator, SchemaValidator
from src.schemas.finrisk import FinRiskRequest
from src.workflows.finrisk_workflow import (
    _CRITICAL_STEPS,
    run_finrisk_workflow,
)
from src.workflows.v16_runner import build_default_engine, run_finrisk_workflow_v16


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


# ---------------------------------------------------------------------------
# Quality-gated orchestrator
# ---------------------------------------------------------------------------


async def test_quality_gated_orchestrator_produces_step_evaluations() -> None:
    engine = build_default_engine()
    state = await run_finrisk_workflow(
        FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
        fixture_path=FIXTURE_PATH,
        quality_engine=engine,
        quality_gated=True,
    )
    # All eight steps must emit a StepEvaluation.
    step_names = {se.step_name for se in state.evaluations}
    assert {
        "company_resolver",
        "filing_risk_extractor",
        "market_explorer",
        "evidence_normalizer",
        "risk_scorer",
        "graph_reasoner",
        "report_generator",
        "evaluator",
    }.issubset(step_names)


async def test_quality_gated_orchestrator_records_v15_trace() -> None:
    """The gated runner must keep emitting the v15 trace events."""
    engine = build_default_engine()
    state = await run_finrisk_workflow(
        FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
        fixture_path=FIXTURE_PATH,
        quality_engine=engine,
        quality_gated=True,
    )
    trace_names = {e.step_name for e in state.trace}
    assert "company_resolver" in trace_names
    assert "evaluator" in trace_names


async def test_workflow_evaluation_aggregates_step_evaluations() -> None:
    state = await run_finrisk_workflow_v16(
        FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
        fixture_path=FIXTURE_PATH,
    )
    # The summary's step_evaluations must align with state.evaluations.
    assert state.workflow_evaluation is not None
    assert (
        state.workflow_evaluation.blocker_count
        == sum(
            1
            for se in state.evaluations
            for f in se.findings
            if f.severity.value == "blocker"
        )
    )


async def test_critical_step_set_is_well_known() -> None:
    """The audit pins six critical steps; the runtime mirrors that set."""
    assert _CRITICAL_STEPS == frozenset(
        {
            "company_resolver",
            "filing_risk_extractor",
            "evidence_normalizer",
            "risk_scorer",
            "report_generator",
            "evaluator",
        }
    )


async def test_quality_gated_orchestrator_works_with_minimal_engine() -> None:
    """A custom engine with a single validator still runs end-to-end."""
    engine = GuardrailEngine(validators=[SchemaValidator()])
    state = await run_finrisk_workflow(
        FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
        fixture_path=FIXTURE_PATH,
        quality_engine=engine,
        quality_gated=True,
    )
    # All steps ran; the demo fixture is well-formed so the report
    # generator must have produced a non-None ``report``.
    assert state.report is not None
    # status reached a terminal value.
    assert state.status in {"completed", "needs_review", "failed"}


async def test_quality_gated_rejects_missing_engine() -> None:
    """`quality_gated=True` without an engine is a programming error."""
    with pytest.raises(ValueError):
        await run_finrisk_workflow(
            FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
            fixture_path=FIXTURE_PATH,
            quality_gated=True,
            quality_engine=None,
        )


async def test_demo_mode_evaluator_records_needs_review_for_diversity() -> None:
    """Demo mode produces at least one needs_review finding (source diversity)."""
    state = await run_finrisk_workflow_v16(
        FinRiskRequest(ticker="AAPL", analysis_goal="test", demo_mode=True),
        fixture_path=FIXTURE_PATH,
    )
    findings = [f for se in state.evaluations for f in se.findings]
    # Either blocker or warning count > 0 is expected because the
    # demo fixture mixes source types. The v17 demo always returns
    # needs_review.
    assert state.workflow_evaluation is not None
    assert (
        state.workflow_evaluation.blocker_count
        + state.workflow_evaluation.warning_count
    ) > 0
