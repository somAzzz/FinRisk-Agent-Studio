"""Evidence validator: every risk must link to at least one evidence row."""

from __future__ import annotations

from typing import Any

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.evaluation.validators.base import Validator
from src.schemas.finrisk import (
    ExtractedRisk,
    FinRiskWorkflowState,
    NormalizedEvidence,
    RiskReport,
)


def _risks_in_output(output: Any) -> list[ExtractedRisk]:
    """Best-effort extraction of a list of risks from a step's output."""
    if isinstance(output, list):
        return [item for item in output if isinstance(item, ExtractedRisk)]
    if isinstance(output, RiskReport):
        return list(output.top_risks)
    if isinstance(output, FinRiskWorkflowState):
        return list(output.filing_risks)
    return []


def _evidence_ids_in_state(state: FinRiskWorkflowState) -> set[str]:
    return {ev.evidence_id for ev in state.normalized_evidence}


class EvidenceValidator:
    """Ensure every top risk has at least one supporting evidence row.

    The check has two halves:

    - If the step produced new risks, the state must already contain
      at least one ``NormalizedEvidence`` row whose
      ``related_risk_ids`` covers each new risk. Risks with no
      supporting evidence get a BLOCKER finding.
    - If the state already carries a ``RiskReport``, every top risk
      is required to have at least one evidence row. Otherwise we
      emit a NEEDS_REVIEW finding.
    """

    name = "evidence"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        findings: list[GuardrailFinding] = []

        # Risks emitted by this step.
        new_risks = _risks_in_output(output)
        if new_risks:
            evidence_by_risk: dict[str, list[NormalizedEvidence]] = {}
            for ev in state.normalized_evidence:
                for rid in ev.related_risk_ids or []:
                    evidence_by_risk.setdefault(rid, []).append(ev)
            for risk in new_risks:
                if not evidence_by_risk.get(risk.risk_id):
                    findings.append(
                        GuardrailFinding(
                            step_name=step_name,
                            check_name=self.name,
                            status=GuardrailStatus.FAIL,
                            severity=GuardrailSeverity.BLOCKER,
                            message=(
                                f"risk {risk.risk_id} has no supporting evidence"
                            ),
                            affected_object_type="risk",
                            affected_object_id=risk.risk_id,
                            recommendation=(
                                "add a NormalizedEvidence row that links to this risk"
                            ),
                        )
                    )

        # Report-level coverage.
        report = state.report
        if report is not None:
            valid_ids = _evidence_ids_in_state(state)
            for risk in report.top_risks:
                if risk.risk_id not in valid_ids:
                    findings.append(
                        GuardrailFinding(
                            step_name=step_name,
                            check_name=self.name,
                            status=GuardrailStatus.NEEDS_REVIEW,
                            severity=GuardrailSeverity.WARNING,
                            message=(
                                f"top risk {risk.risk_id} lacks direct evidence"
                            ),
                            affected_object_type="risk",
                            affected_object_id=risk.risk_id,
                        )
                    )
        return findings


__all__ = ["EvidenceValidator"]
