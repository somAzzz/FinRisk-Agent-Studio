"""Tests for the v16 graph context builder."""

from __future__ import annotations

from src.graph_reasoning import build_graph_context
from src.schemas.finrisk import (
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    CompanyProfile,
    utcnow,
)


def _state(*, risk_types: list[str]) -> FinRiskWorkflowState:
    risks = [
        ExtractedRisk(
            risk_id=f"r-{i}",
            risk_type=rt,
            risk_factor=f"factor {i}",
            severity=3,
            evidence_quote="q",
            source="sec_filing:test",
            filing_section="section_1a",
            confidence=0.7,
        )
        for i, rt in enumerate(risk_types)
    ]
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="supply chain risk", demo_mode=True),
        company=CompanyProfile(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            filing_type="10-K",
            analysis_year=2024,
            source="fixture",
            resolved_at=utcnow(),
        ),
        filing_risks=risks,
    )


def test_context_builder_emits_company_id() -> None:
    ctx = build_graph_context(_state(risk_types=["policy"]))
    assert ctx.company_id == "company:AAPL"
    assert ctx.ticker == "AAPL"


def test_context_builder_maps_risk_types_to_edge_types() -> None:
    ctx = build_graph_context(_state(risk_types=["supply_chain", "policy"]))
    assert "DEPENDS_ON" in ctx.allowed_edge_types
    assert "REGULATED_BY" in ctx.allowed_edge_types
    # Always include AFFECTS for fallback paths.
    assert "AFFECTS" in ctx.allowed_edge_types


def test_context_builder_includes_focus_entities() -> None:
    ctx = build_graph_context(_state(risk_types=["policy"]))
    assert "Apple Inc." in ctx.focus_entities
    assert "policy" in ctx.focus_entities
