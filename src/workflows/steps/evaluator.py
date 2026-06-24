"""Step 8: workflow evaluator / guardrails.

Performs code-level checks on the final report and sets ``state.status``
plus ``state.evaluation``. The evaluator never raises; the orchestrator
relies on ``state.evaluation.final_status`` for the verdict.
"""

from __future__ import annotations

import re

from src.workflows.state import (
    EvaluationStatus,
    FinRiskWorkflowState,
    WorkflowEvaluation,
)
from src.workflows.steps._base import WorkflowStep


_FORBIDDEN_PHRASES = (
    "buy now",
    "must rise",
    "guaranteed return",
    "sell now",
)

_INVESTMENT_ADVICE_PATTERNS = (
    re.compile(r"\bbuy\b\s+(?:the\s+)?(?:stock|shares)", re.IGNORECASE),
    re.compile(r"\bsell\b\s+(?:the\s+)?(?:stock|shares)", re.IGNORECASE),
    re.compile(r"\bstrong\s+buy\b", re.IGNORECASE),
    re.compile(r"\bstrong\s+sell\b", re.IGNORECASE),
)


class EvaluatorStep(WorkflowStep):
    """Run guardrails on the generated report and emit a ``WorkflowEvaluation``."""

    name = "evaluator"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        report = state.report
        if report is None:
            state.evaluation = WorkflowEvaluation(
                schema_valid=False,
                has_evidence_for_each_risk=False,
                unsupported_claims=["report is missing"],
                financial_advice_risk=False,
                source_diversity_score=0.0,
                hallucination_risk_score=1.0,
                final_status="fail",
            )
            state.status = "failed"
            return state

        # 1. severity range
        severity_valid = all(1 <= r.severity <= 5 for r in report.top_risks)
        schema_valid = severity_valid

        # 2. each risk has evidence
        evidence_ids = {ev.evidence_id for ev in report.evidence_table}
        related_per_risk = {
            r.risk_id: {
                ev.evidence_id
                for ev in report.evidence_table
                if r.risk_id in (ev.related_risk_ids or [])
            }
            for r in report.top_risks
        }
        unsupported = [
            r.risk_id
            for r in report.top_risks
            if not related_per_risk[r.risk_id]
        ]
        # Drop the unsupported risk list from unsupported_claims (it's
        # already represented via has_evidence_for_each_risk below).
        unsupported_claims: list[str] = []

        # 3. financial-advice risk scan
        body = report.markdown.lower()
        advice_risk = any(phrase in body for phrase in _FORBIDDEN_PHRASES)
        for pattern in _INVESTMENT_ADVICE_PATTERNS:
            if pattern.search(report.markdown):
                advice_risk = True
                break

        # 4. source diversity
        sources = {ev.source_type for ev in report.evidence_table}
        diversity = min(1.0, len(sources) / 3.0)

        # 5. hallucination heuristic: markdown contains unsupported claims
        #    i.e. risk factors without an evidence row.
        hallucination_risk = (
            min(1.0, len(unsupported) / max(1, len(report.top_risks))) if report.top_risks else 0.0
        )

        verdict: EvaluationStatus = "pass"
        if not severity_valid or unsupported or advice_risk or not schema_valid:
            verdict = "needs_review"
        if hallucination_risk >= 0.5 or advice_risk:
            verdict = "needs_review"
        if len(report.top_risks) == 0 or not evidence_ids:
            verdict = "fail"

        evaluation = WorkflowEvaluation(
            schema_valid=schema_valid,
            has_evidence_for_each_risk=not unsupported,
            unsupported_claims=unsupported_claims,
            financial_advice_risk=advice_risk,
            source_diversity_score=round(diversity, 4),
            hallucination_risk_score=round(hallucination_risk, 4),
            final_status=verdict,
        )
        state.evaluation = evaluation

        # Map verdict to workflow status.
        if verdict == "pass":
            state.status = "completed"
        elif verdict == "needs_review":
            state.status = "needs_review"
        else:
            state.status = "failed"

        return state


__all__ = ["EvaluatorStep"]