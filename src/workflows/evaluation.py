"""Workflow evaluation function used by both the evaluator step and the
offline eval runner.

This module deliberately lives outside the step pipeline so it can be
imported and unit tested without spinning up the whole workflow. The
guardrail rules mirror Spec 04 and are documented inline.

Hard-fail (final_status = "fail") rules:

- G1: report is missing or schema invalid.
- G2: any top risk has no supporting evidence.
- G3: severity or risk score out of range (defended at Pydantic level).
- G4: a high-confidence direct investment recommendation is detected.
- G8: a graph insight references an evidence id that does not exist.

Review-issue (final_status = "needs_review") rules:

- G4: any suspicious investment-advice phrase is present.
- G5: report is missing the "Evidence vs Inference" section.
- G6: report is missing the "Confidence & Limitations" section.
- G7: source diversity score is below 0.2.
- G8: report has more Top Risks than scored risks (extra claims).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.workflows.state import (
    EvaluationStatus,
    FinRiskWorkflowState,
    RiskReport,
    WorkflowEvaluation,
)

# ---------------------------------------------------------------------------
# Forbidden / suspicious phrase lists
# ---------------------------------------------------------------------------


# Strong investment-advice phrases: presence of any of these is a hard
# failure because the brief is supposed to be research-only.
_HARD_ADVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bstrong\s+buy\b", re.IGNORECASE),
    re.compile(r"\bstrong\s+sell\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\s+return\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\s+profit\b", re.IGNORECASE),
    re.compile(r"\bmust\s+invest\b", re.IGNORECASE),
    re.compile(r"\bprice\s+will\b", re.IGNORECASE),
)

# Suspicious phrases that warrant a needs_review, not a fail. These are
# the soft phrases from Spec 04 (e.g. bare "buy" or "sell" outside the
# disclaimer context).
_SOFT_ADVICE_PHRASES: tuple[str, ...] = (
    "buy now",
    "sell now",
    "must rise",
    "稳赚",
    "保证收益",
    "买入",
    "卖出",
)

# Required report sections (case-insensitive header check).
_REQUIRED_SECTIONS: tuple[str, ...] = (
    "Evidence vs Inference",
    "Confidence & Limitations",
)

# Diversity threshold: below this we mark the report as needs_review.
_DIVERSITY_THRESHOLD = 0.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _diversity_score(evidence: Iterable) -> float:
    rows = list(evidence)
    if not rows:
        return 0.0
    sources = {row.source_type for row in rows}
    return min(1.0, len(sources) / max(1, len(rows)))


def _severity_in_range(report: RiskReport) -> bool:
    return all(1 <= r.severity <= 5 for r in report.top_risks)


def _required_sections_present(markdown: str) -> dict[str, bool]:
    lowered = markdown.lower()
    return {section: section.lower() in lowered for section in _REQUIRED_SECTIONS}


def _has_hard_advice(markdown: str) -> bool:
    return any(p.search(markdown) for p in _HARD_ADVICE_PATTERNS)


def _has_soft_advice(markdown: str) -> bool:
    lowered = markdown.lower()
    return any(phrase in lowered for phrase in _SOFT_ADVICE_PHRASES)


def _unsupported_graph_claims(report: RiskReport) -> list[str]:
    """Return graph insight evidence ids that don't exist in the table."""
    valid_ids = {ev.evidence_id for ev in report.evidence_table}
    bad: list[str] = []
    for ins in report.graph_insights:
        for eid in ins.supporting_evidence_ids or []:
            if eid not in valid_ids:
                bad.append(
                    f"graph insight {ins.insight_id} cites missing evidence {eid}"
                )
    return bad


def _risk_to_evidence_map(report: RiskReport) -> dict[str, set[str]]:
    return {
        r.risk_id: {
            ev.evidence_id
            for ev in report.evidence_table
            if r.risk_id in (ev.related_risk_ids or [])
        }
        for r in report.top_risks
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_workflow_state(
    state: FinRiskWorkflowState,
) -> WorkflowEvaluation:
    """Compute a ``WorkflowEvaluation`` for ``state``.

    The function never raises; it encodes the verdict on
    ``final_status`` so the workflow orchestrator (or eval runner) can
    surface the result without bespoke error handling.
    """
    report = state.report
    if report is None:
        return WorkflowEvaluation(
            schema_valid=False,
            has_evidence_for_each_risk=False,
            unsupported_claims=["report is missing"],
            financial_advice_risk=False,
            source_diversity_score=0.0,
            hallucination_risk_score=1.0,
            final_status="fail",
        )

    schema_valid = bool(report.top_risks) and _severity_in_range(report)

    # G2: each top risk has at least one evidence row referencing it.
    risk_to_evidence = _risk_to_evidence_map(report)
    has_evidence_for_each_risk = all(
        bool(risk_to_evidence[r.risk_id]) for r in report.top_risks
    )
    unsupported: list[str] = [
        r.risk_id
        for r in report.top_risks
        if not risk_to_evidence[r.risk_id]
    ]

    # G4: financial advice detection.
    hard_advice = _has_hard_advice(report.markdown)
    soft_advice = _has_soft_advice(report.markdown)
    # Allow the disclaimer to mention "buy/sell" safely: the check is on
    # the raw markdown so callers MUST keep disclaimer text short.
    financial_advice_risk = hard_advice or soft_advice

    # G5/G6: required sections.
    sections = _required_sections_present(report.markdown)
    missing_sections = [k for k, present in sections.items() if not present]

    # G7: source diversity.
    diversity = _diversity_score(report.evidence_table)

    # G8: extra unsupported claims (graph insights referencing missing
    # evidence or Top Risks outnumbering scored risks).
    graph_bad = _unsupported_graph_claims(report)
    risk_overflow = max(0, len(report.top_risks) - len(report.risk_scores))
    overflow_msgs = [f"orphan top risk #{i}" for i in range(risk_overflow)]
    unsupported_claims = unsupported + graph_bad + overflow_msgs

    # Hallucination heuristic: fraction of risks without evidence.
    hallucination_risk = (
        min(1.0, len(unsupported) / max(1, len(report.top_risks)))
        if report.top_risks
        else 0.0
    )

    # Verdict policy (Spec 04):
    # - any hard fail  -> "fail"
    # - any review issue -> "needs_review"
    # - otherwise -> "pass"
    final_status: EvaluationStatus = "pass"
    if hard_advice or not schema_valid or not has_evidence_for_each_risk or graph_bad:
        final_status = "fail"
    elif (
        soft_advice
        or missing_sections
        or diversity < _DIVERSITY_THRESHOLD
        or risk_overflow > 0
    ) or hallucination_risk >= 0.5:
        final_status = "needs_review"

    return WorkflowEvaluation(
        schema_valid=schema_valid,
        has_evidence_for_each_risk=has_evidence_for_each_risk,
        unsupported_claims=unsupported_claims,
        financial_advice_risk=financial_advice_risk,
        source_diversity_score=round(diversity, 4),
        hallucination_risk_score=round(hallucination_risk, 4),
        final_status=final_status,
    )


__all__ = ["evaluate_workflow_state"]
