"""Structured v16 report models and score adapters."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.evaluation.claim_grounding import Claim
from src.graph_reasoning.models import GraphInsightV16
from src.research.risk_impact import RiskFinancialImpact


class RiskScoreV16(BaseModel):
    """Canonical research-priority score on a 0-100 scale."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    base_severity: float = Field(ge=0.0, le=1.0)
    recent_signal_strength: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    source_diversity: float = Field(ge=0.0, le=1.0)
    novelty_score: float = Field(ge=0.0, le=1.0)
    novelty_available: bool = True
    graph_centrality: float = Field(default=0.0, ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    component_availability: dict[str, bool] = Field(default_factory=dict)
    reasoning: str = ""


class RiskReportItem(BaseModel):
    """One top-risk row in the structured report."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    title: str
    risk_type: str
    severity: int = Field(ge=1, le=5)
    final_score: float = Field(ge=0.0, le=100.0)
    summary: str
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    related_graph_insight_ids: list[str] = Field(default_factory=list)
    # Lifecycle classification (added 2026-06-25). Surfaced on the
    # frontend as a ``LifecycleBadge`` (green=current, amber=emerging,
    # gray=receding). Populated by ``LifecycleClassifierStep``;
    # missing for risks classified before the step was added.
    lifecycle: Literal["current", "emerging", "receding", "unknown"] = "unknown"
    lifecycle_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    lifecycle_reasoning: str = ""


class RecentChange(BaseModel):
    """A recent market or transcript signal cited by the report."""

    model_config = ConfigDict(extra="forbid")

    change_id: str
    text: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceReference(BaseModel):
    """Compact evidence reference used by the frontend report view."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_name: str
    source_url: str | None = None
    quote_or_summary: str
    source_quality_score: float = Field(ge=0.0, le=1.0)


class RiskReportV16(BaseModel):
    """Structured v16 risk intelligence brief."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    title: str
    executive_summary: str
    top_risks: list[RiskReportItem] = Field(default_factory=list)
    recent_changes: list[RecentChange] = Field(default_factory=list)
    evidence_table: list[EvidenceReference] = Field(default_factory=list)
    second_order_effects: list[GraphInsightV16] = Field(default_factory=list)
    evidence_vs_inference: list[Claim] = Field(default_factory=list)
    financial_impacts: list[RiskFinancialImpact] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_next_questions: list[str] = Field(default_factory=list)
    disclaimer: str
    markdown: str | None = None


def _clamp01(value: Any) -> float:
    """Best-effort clamp to the unit interval."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def normalise_severity(severity: int | float) -> float:
    """Map a 1-5 severity value onto the unit interval."""
    try:
        raw = float(severity)
    except (TypeError, ValueError):
        raw = 1.0
    return _clamp01((raw - 1.0) / 4.0)


def compute_risk_score_v16(score: Any) -> RiskScoreV16:
    """Convert a legacy ``RiskScore`` into the v16 0-100 score model."""
    components = {
        "base_severity": normalise_severity(getattr(score, "base_severity", 1)),
        "recent_signal_strength": _clamp01(
            getattr(score, "recent_signal_strength", 0.0)
        ),
        "evidence_quality": _clamp01(getattr(score, "evidence_quality", 0.0)),
        "source_diversity": _clamp01(getattr(score, "source_diversity", 0.0)),
        "novelty_score": _clamp01(getattr(score, "novelty_score", 0.0)),
        "graph_centrality": _clamp01(getattr(score, "graph_centrality", 0.0)),
    }
    weights = {
        "base_severity": 0.30,
        "recent_signal_strength": 0.20,
        "evidence_quality": 0.20,
        "source_diversity": 0.10,
        "novelty_score": 0.10,
        "graph_centrality": 0.10,
    }
    availability = dict.fromkeys(components, True)
    availability["novelty_score"] = bool(
        getattr(score, "novelty_available", True)
    )
    active_weight = sum(
        weight for key, weight in weights.items() if availability[key]
    )
    weighted = {
        key: round(
            components[key]
            * (weights[key] / active_weight if availability[key] else 0.0)
            * 100.0,
            4,
        )
        for key in components
    }
    final_score = round(sum(weighted.values()), 4)
    return RiskScoreV16(
        risk_id=str(getattr(score, "risk_id", "")),
        **components,
        novelty_available=availability["novelty_score"],
        final_score=max(0.0, min(100.0, final_score)),
        score_breakdown=weighted,
        component_availability=availability,
        reasoning=str(
            getattr(score, "score_reasoning", "")
            or "deterministic weighted v16 score"
        ),
    )


__all__ = [
    "EvidenceReference",
    "RecentChange",
    "RiskReportItem",
    "RiskReportV16",
    "RiskScoreV16",
    "compute_risk_score_v16",
    "normalise_severity",
]
