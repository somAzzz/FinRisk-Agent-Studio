"""Tests for the v16 risk scoring formula."""

from __future__ import annotations

from src.reports import compute_risk_score_v16, normalise_severity
from src.schemas.finrisk import RiskScore


def test_normalise_severity_maps_1_to_5_to_unit_interval() -> None:
    assert normalise_severity(1) == 0.0
    assert normalise_severity(3) == 0.5
    assert normalise_severity(5) == 1.0


def test_compute_risk_score_v16_returns_zero_to_hundred() -> None:
    score = RiskScore(
        risk_id="r-1",
        base_severity=4,
        recent_signal_strength=0.6,
        evidence_quality=0.8,
        source_diversity=0.7,
        novelty_score=0.5,
        graph_centrality=0.4,
        final_score=0.5,
        score_reasoning="baseline",
    )
    v16 = compute_risk_score_v16(score)
    assert 0.0 <= v16.final_score <= 100.0


def test_compute_risk_score_v16_is_deterministic() -> None:
    score = RiskScore(
        risk_id="r-1",
        base_severity=3,
        recent_signal_strength=0.5,
        evidence_quality=0.5,
        source_diversity=0.5,
        novelty_score=0.5,
        graph_centrality=0.0,
        final_score=0.0,
        score_reasoning="x",
    )
    a = compute_risk_score_v16(score)
    b = compute_risk_score_v16(score)
    assert a.final_score == b.final_score
    assert a.score_breakdown == b.score_breakdown


def test_compute_risk_score_v16_breaks_down_all_components() -> None:
    score = RiskScore(
        risk_id="r-1",
        base_severity=5,
        recent_signal_strength=1.0,
        evidence_quality=1.0,
        source_diversity=1.0,
        novelty_score=1.0,
        graph_centrality=1.0,
        final_score=0.0,
        score_reasoning="x",
    )
    v16 = compute_risk_score_v16(score)
    expected_keys = {
        "base_severity",
        "recent_signal_strength",
        "evidence_quality",
        "source_diversity",
        "novelty_score",
        "graph_centrality",
    }
    assert expected_keys.issubset(v16.score_breakdown)
    # With every component at 1.0 we should hit the 100-point ceiling.
    assert v16.final_score == 100.0


def test_compute_risk_score_v16_handles_zero_components() -> None:
    score = RiskScore(
        risk_id="r-1",
        base_severity=1,
        recent_signal_strength=0.0,
        evidence_quality=0.0,
        source_diversity=0.0,
        novelty_score=0.0,
        graph_centrality=0.0,
        final_score=0.0,
        score_reasoning="x",
    )
    v16 = compute_risk_score_v16(score)
    assert v16.final_score == 0.0
