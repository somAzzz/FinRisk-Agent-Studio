"""Unit tests for the v16 guardrail engine and validators."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src.evaluation.engine import GuardrailEngine
from src.evaluation.models import (
    FallbackEvent,
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
    StepEvaluation,
    WorkflowEvaluationV16,
    build_workflow_evaluation,
)
from src.evaluation.validators import (
    EvidenceValidator,
    FinancialSafetyValidator,
    ReportStructureValidator,
    SchemaValidator,
    WorkflowValidator,
)
from src.schemas.finrisk import (
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    RiskReport,
    utcnow,
)
from src.workflows.state import WorkflowTraceEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**overrides) -> FinRiskWorkflowState:
    defaults: dict = dict(
        run_id="run-1",
        request=FinRiskRequest(
            ticker="AAPL", analysis_goal="test goal", demo_mode=True
        ),
    )
    defaults.update(overrides)
    return FinRiskWorkflowState(**defaults)


def _sample_risk(risk_id: str = "r-1") -> ExtractedRisk:
    return ExtractedRisk(
        risk_id=risk_id,
        risk_type="policy",
        risk_factor="Sample factor",
        severity=3,
        evidence_quote="quote",
        source="sec_filing:test",
        filing_section="section_1a",
        confidence=0.8,
    )


def _sample_evidence(evidence_id: str = "ne-r-1") -> NormalizedEvidence:
    return NormalizedEvidence(
        evidence_id=evidence_id,
        source_type="filing",
        source_name="10-K",
        source_url=None,
        quote="quote",
        summary="summary",
        related_risk_ids=["r-1"],
        credibility_score=0.9,
        collected_at=utcnow(),
    )


# ---------------------------------------------------------------------------
# Engine: pre/post / aggregation
# ---------------------------------------------------------------------------


def test_engine_validate_post_step_appends_evaluation() -> None:
    engine = GuardrailEngine(validators=[SchemaValidator()])
    state = _state()
    evaluation = engine.validate_post_step("company_resolver", state, state)
    assert evaluation.step_name == "company_resolver"
    assert evaluation.status == GuardrailStatus.PASS
    assert state.evaluations[0] is evaluation


def test_engine_records_fallback_event_when_requested() -> None:
    engine = GuardrailEngine(validators=[SchemaValidator()])
    state = _state()
    engine.validate_post_step(
        "market_explorer", state, state, fallback_used="cached"
    )
    assert state.fallback_events and state.fallback_events[0].to_mode == "cached"


def test_engine_summarizes_to_workflow_evaluation() -> None:
    engine = GuardrailEngine()
    state = _state()
    state.evaluations.append(
        StepEvaluation(
            step_name="filing_risk_extractor",
            status=GuardrailStatus.PASS,
            findings=[],
        )
    )
    state.evaluations.append(
        StepEvaluation(
            step_name="evaluator",
            status=GuardrailStatus.WARNING,
            findings=[
                GuardrailFinding(
                    step_name="evaluator",
                    check_name="financial_safety",
                    status=GuardrailStatus.NEEDS_REVIEW,
                    severity=GuardrailSeverity.WARNING,
                    message="soft phrase",
                    affected_object_type="report_section",
                )
            ],
        )
    )
    summary = engine.summarize_workflow(state)
    assert isinstance(summary, WorkflowEvaluationV16)
    assert summary.final_status == GuardrailStatus.NEEDS_REVIEW
    assert summary.warning_count == 1
    assert summary.human_review_required is True


def test_engine_validator_exception_becomes_finding() -> None:
    class BoomValidator:
        name = "boom"

        def validate(self, step_name, output, state):
            raise RuntimeError("kaboom")

    engine = GuardrailEngine(validators=[BoomValidator()])
    state = _state()
    evaluation = engine.validate_post_step("company_resolver", state, state)
    assert evaluation.status == GuardrailStatus.FAIL
    assert evaluation.findings and "kaboom" in evaluation.findings[0].message


# ---------------------------------------------------------------------------
# build_workflow_evaluation helper
# ---------------------------------------------------------------------------


def test_build_workflow_evaluation_with_no_steps_passes() -> None:
    summary = build_workflow_evaluation(run_id="r", step_evaluations=[])
    assert summary.final_status == GuardrailStatus.PASS
    assert summary.blocker_count == 0
    assert summary.human_review_required is False


# ---------------------------------------------------------------------------
# SchemaValidator
# ---------------------------------------------------------------------------


class _GoodModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(ge=0)


def test_schema_validator_passes_for_pydantic_model() -> None:
    findings = SchemaValidator().validate("step", _GoodModel(x=1), _state())
    assert findings == []


def test_schema_validator_blocks_none_output() -> None:
    findings = SchemaValidator().validate("step", None, _state())
    assert findings[0].severity == GuardrailSeverity.BLOCKER


def test_schema_validator_blocks_non_pydantic_output() -> None:
    findings = SchemaValidator().validate("step", "not a model", _state())
    assert findings[0].severity == GuardrailSeverity.BLOCKER


# ---------------------------------------------------------------------------
# EvidenceValidator
# ---------------------------------------------------------------------------


def test_evidence_validator_passes_when_risks_have_evidence() -> None:
    risk = _sample_risk()
    ev = _sample_evidence()
    state = _state(normalized_evidence=[ev])
    findings = EvidenceValidator().validate("step", [risk], state)
    assert findings == []


def test_evidence_validator_blocks_risk_without_evidence() -> None:
    risk = _sample_risk("r-orphan")
    state = _state(normalized_evidence=[])
    findings = EvidenceValidator().validate("step", [risk], state)
    assert findings and findings[0].severity == GuardrailSeverity.BLOCKER


# ---------------------------------------------------------------------------
# FinancialSafetyValidator
# ---------------------------------------------------------------------------


def test_financial_safety_validator_flags_soft_phrase() -> None:
    risk = _sample_risk()
    report = RiskReport(
        title="t",
        executive_summary="buy now",
        top_risks=[risk],
        risk_scores=[],
        evidence_table=[],
        graph_insights=[],
        evidence_vs_inference="evidence vs inference",
        limitations="limitations",
        recommended_next_questions=[],
        markdown="## Executive Summary\nbuy now",
    )
    state = _state(report=report)
    findings = FinancialSafetyValidator().validate("report", report.markdown, state)
    assert findings and findings[0].severity == GuardrailSeverity.WARNING


def test_financial_safety_validator_flags_hard_phrase() -> None:
    risk = _sample_risk()
    report = RiskReport(
        title="t",
        executive_summary="summary",
        top_risks=[risk],
        risk_scores=[],
        evidence_table=[],
        graph_insights=[],
        evidence_vs_inference="evidence vs inference",
        limitations="limitations",
        recommended_next_questions=[],
        markdown="## Disclaimer\nstrong buy coming\nThis is not investment advice",
    )
    state = _state(report=report)
    findings = FinancialSafetyValidator().validate("report", None, state)
    assert findings and findings[0].severity == GuardrailSeverity.ERROR


# ---------------------------------------------------------------------------
# ReportStructureValidator
# ---------------------------------------------------------------------------


def test_report_structure_validator_flags_missing_sections() -> None:
    report = RiskReport(
        title="t",
        executive_summary="",
        top_risks=[],
        risk_scores=[],
        evidence_table=[],
        graph_insights=[],
        evidence_vs_inference="placeholder",
        limitations="placeholder",
        recommended_next_questions=[],
        markdown="## Title\nNothing here",
    )
    state = _state(report=report)
    findings = ReportStructureValidator().validate("report", None, state)
    assert any(f.severity == GuardrailSeverity.BLOCKER for f in findings)


# ---------------------------------------------------------------------------
# WorkflowValidator
# ---------------------------------------------------------------------------


def test_workflow_validator_flags_empty_run_id() -> None:
    # Bypass FinRiskWorkflowState's model validation by hand-crafting
    # a state via model_construct to exercise the validator branch.
    state = _state()
    object.__setattr__(state, "run_id", "")
    findings = WorkflowValidator().validate("workflow", state, state)
    assert findings and findings[0].severity == GuardrailSeverity.BLOCKER
