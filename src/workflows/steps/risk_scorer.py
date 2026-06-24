"""Step 5: deterministic risk scoring."""

from __future__ import annotations

from src.workflows.state import (
    FinRiskWorkflowState,
    RiskScore,
)
from src.workflows.steps._base import WorkflowStep


def compute_risk_score(risk, normalized_evidence) -> RiskScore:
    """Compute the deterministic final score for one risk.

    The formula is intentionally simple and explainable so reviewers
    can audit the math without consulting an LLM. LLM is reserved for
    the human-readable ``score_reasoning`` field, never the score.
    """
    base_severity = risk.severity
    base = base_severity / 5.0

    related = [
        ev
        for ev in normalized_evidence
        if risk.risk_id in (ev.related_risk_ids or [])
    ]
    recent_signal = (
        min(1.0, len([e for e in related if e.source_type == "web"]) / 2.0)
        if related
        else 0.0
    )
    supporting = [e for e in related if "supports" in e.summary.lower()]
    contradicting = [
        e for e in related if "contradicts" in e.summary.lower()
    ]
    base_evidence_quality = 0.7 if related else 0.0
    quality_adjustment = (
        0.2 if contradicting and not supporting else 0.0
    )
    evidence_quality = max(
        0.0, min(1.0, base_evidence_quality - quality_adjustment)
    )

    sources = {ev.source_type for ev in related}
    source_diversity = min(1.0, len(sources) / 3.0)

    novelty = 0.5  # baseline; future step can compare with prior runs

    final_score = round(
        min(
            1.0,
            max(
                0.0,
                0.35 * base
                + 0.25 * recent_signal
                + 0.20 * evidence_quality
                + 0.10 * source_diversity
                + 0.10 * novelty,
            ),
        ),
        4,
    )

    reasoning = (
        f"severity={base_severity}/5; "
        f"recent_signals={int(recent_signal * 2)}; "
        f"evidence_quality={evidence_quality:.2f}; "
        f"source_diversity={len(sources)}"
    )

    return RiskScore(
        risk_id=risk.risk_id,
        base_severity=base_severity,
        recent_signal_strength=round(recent_signal, 4),
        evidence_quality=round(evidence_quality, 4),
        source_diversity=round(source_diversity, 4),
        novelty_score=novelty,
        final_score=final_score,
        score_reasoning=reasoning,
    )


class RiskScorerStep(WorkflowStep):
    """Score every filing risk using the deterministic formula above."""

    name = "risk_scorer"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        scores = [
            compute_risk_score(risk, state.normalized_evidence)
            for risk in state.filing_risks
        ]
        state.risk_scores = scores
        return state


__all__ = ["RiskScorerStep", "compute_risk_score"]