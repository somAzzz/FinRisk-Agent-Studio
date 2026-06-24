"""Schema-level tests for the FinRisk Agent Studio workflow."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.finrisk import (
    CompanyProfile,
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    GraphInsight,
    MarketEvidence,
    NormalizedEvidence,
    RiskReport,
    RiskScore,
    WorkflowEvaluation,
    WorkflowTraceEvent,
    utcnow,
)


def _make_risk(severity: int = 3) -> ExtractedRisk:
    return ExtractedRisk(
        risk_id="risk-1",
        risk_type="supply_chain",
        risk_factor="Asia supplier concentration.",
        severity=severity,
        evidence_quote="We depend on suppliers in Asia.",
        source="sec_filing",
        filing_section="section_1a",
        confidence=0.8,
    )


def test_request_normalizes_ticker() -> None:
    req = FinRiskRequest(
        ticker="  aapl ",
        analysis_goal="Identify supply-chain risks.",
    )
    assert req.ticker == "AAPL"


def test_request_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        FinRiskRequest(ticker="AAPL", analysis_goal="   ")


def test_request_rejects_negative_max_browser_steps() -> None:
    with pytest.raises(ValidationError):
        FinRiskRequest(
            ticker="AAPL", analysis_goal="x", max_browser_steps=-1
        )


def test_request_rejects_empty_sources() -> None:
    with pytest.raises(ValidationError):
        FinRiskRequest(
            ticker="AAPL", analysis_goal="x", sources=[]
        )


def test_request_dedupes_sources_preserving_order() -> None:
    req = FinRiskRequest(
        ticker="AAPL",
        analysis_goal="x",
        sources=["filing", "web", "filing"],
    )
    assert req.sources == ["filing", "web"]


def test_extracted_risk_rejects_severity_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _make_risk(severity=0)
    with pytest.raises(ValidationError):
        _make_risk(severity=6)


def test_extracted_risk_rejects_empty_evidence_quote() -> None:
    with pytest.raises(ValidationError):
        ExtractedRisk(
            risk_id="r",
            risk_type="macro",
            risk_factor="x",
            severity=3,
            evidence_quote="   ",
            source="src",
            confidence=0.5,
        )


def test_company_profile_uppercases_ticker_and_pads_cik() -> None:
    prof = CompanyProfile(
        company_name="Apple Inc.",
        ticker="aapl",
        cik="320193",
        resolved_at=utcnow(),
    )
    assert prof.ticker == "AAPL"
    assert prof.cik == "0000320193"


def test_market_evidence_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        MarketEvidence(
            evidence_id="m1",
            source_url="not-a-url",
            source_type="news",
            claim="x",
            evidence_summary="x",
            confidence=0.5,
            timestamp=utcnow(),
        )


def test_market_evidence_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        MarketEvidence(
            evidence_id="m1",
            source_url="https://example.com/a",
            source_type="news",
            claim="x",
            evidence_summary="x",
            confidence=1.5,
            timestamp=utcnow(),
        )


def test_normalized_evidence_passes() -> None:
    ne = NormalizedEvidence(
        evidence_id="ne-1",
        source_type="filing",
        source_name="AAPL 10-K",
        source_url="https://www.sec.gov/aapl",
        summary="Supply chain disruption risk.",
        credibility_score=0.9,
        collected_at=utcnow(),
    )
    assert ne.evidence_id == "ne-1"


def test_risk_score_computes_within_bounds() -> None:
    score = RiskScore(
        risk_id="risk-1",
        base_severity=4,
        recent_signal_strength=0.7,
        evidence_quality=0.8,
        source_diversity=0.6,
        novelty_score=0.5,
        final_score=0.72,
        score_reasoning="Composite of severity, evidence, and signal.",
    )
    assert 0.0 <= score.final_score <= 1.0


def test_graph_insight_requires_two_path_nodes() -> None:
    with pytest.raises(ValidationError):
        GraphInsight(
            insight_id="g1",
            source_company="Apple",
            affected_entity="TSMC",
            risk_path=["Apple"],
            supporting_evidence_ids=["e1"],
            confidence=0.5,
        )


def test_graph_insight_with_two_path_nodes() -> None:
    g = GraphInsight(
        insight_id="g1",
        source_company="Apple",
        affected_entity="TSMC",
        risk_path=["Apple", "TSMC"],
        supporting_evidence_ids=["e1"],
        confidence=0.5,
    )
    assert len(g.risk_path) == 2


def test_risk_report_requires_limitations_and_evidence_vs_inference() -> None:
    risk = _make_risk()
    with pytest.raises(ValidationError):
        RiskReport(
            title="Apple Risk Brief",
            executive_summary="Top risks for Apple.",
            top_risks=[risk],
            risk_scores=[],
            evidence_table=[],
            graph_insights=[],
            evidence_vs_inference="   ",
            limitations="",
            recommended_next_questions=[],
            markdown="# Brief",
        )


def test_workflow_trace_event_records_step_lifecycle() -> None:
    started = utcnow()
    completed = datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc)
    event = WorkflowTraceEvent(
        step_name="company_resolver",
        status="completed",
        started_at=started,
        completed_at=completed,
        input_summary="AAPL",
        output_summary="Apple Inc. (0000320193)",
    )
    assert event.retry_count == 0


def test_workflow_state_serializes_to_json() -> None:
    req = FinRiskRequest(ticker="AAPL", analysis_goal="x")
    state = FinRiskWorkflowState(run_id="run-1", request=req)
    payload = state.model_dump_json()
    round_tripped = FinRiskWorkflowState.model_validate_json(payload)
    assert round_tripped.run_id == "run-1"
    assert round_tripped.request.ticker == "AAPL"
    assert round_tripped.status == "created"


def test_evaluation_requires_final_status() -> None:
    ev = WorkflowEvaluation(
        schema_valid=True,
        has_evidence_for_each_risk=True,
        unsupported_claims=[],
        financial_advice_risk=False,
        source_diversity_score=0.7,
        hallucination_risk_score=0.2,
        final_status="pass",
    )
    assert ev.final_status == "pass"


def test_workflow_state_finrisk_request_defaults() -> None:
    """Default ``sources`` includes filing/web/graph and time horizon is 6-12 months."""
    state = FinRiskWorkflowState(
        run_id="r", request=FinRiskRequest(ticker="AAPL", analysis_goal="x")
    )
    assert state.request.sources == ["filing", "web", "graph"]
    assert state.request.time_horizon == "6-12 months"