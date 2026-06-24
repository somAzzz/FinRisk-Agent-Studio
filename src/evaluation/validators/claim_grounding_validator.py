"""Claim grounding validator.

Layered checks per v16 spec 02:

- Layer 1 (rule): every claim must have at least one
  ``supporting_evidence_id`` and every cited id must exist in
  ``state.normalized_evidence``.
- Layer 2 (lexical overlap): each claim's tokens must overlap
  with at least one of its cited evidence rows above the
  ``grounded`` threshold (``0.25``).
- Layer 3 (LLM/NLI judge) is intentionally a no-op in v16.

Findings follow the v16 status/severity conventions:
``BLOCKER`` for missing evidence, ``ERROR`` for Layer 1 violations,
``WARNING`` for Layer 2 warnings.
"""

from __future__ import annotations

from typing import Any

from src.evaluation.claim_grounding import (
    Claim,
    grounding_label,
    lexical_overlap,
)
from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.evaluation.validators.base import Validator
from src.schemas.finrisk import FinRiskWorkflowState, NormalizedEvidence


def _evidence_text(ev: NormalizedEvidence) -> str:
    return " ".join(filter(None, [ev.quote, ev.summary]))


def _evidence_by_id(state: FinRiskWorkflowState) -> dict[str, NormalizedEvidence]:
    return {ev.evidence_id: ev for ev in state.normalized_evidence}


class ClaimGroundingValidator:
    name = "claim_grounding"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        # Collect claims either from the step output or from the
        # state. Step output takes precedence so the validator can
        # be invoked per-step.
        claims: list[Claim] = []
        if isinstance(output, list):
            claims = [c for c in output if isinstance(c, Claim)]
        elif isinstance(output, Claim):
            claims = [output]
        if not claims and state.claims:
            claims = [
                Claim.model_validate(c) if not isinstance(c, Claim) else c
                for c in state.claims
            ]
        if not claims:
            return []

        evidence_by_id = _evidence_by_id(state)
        findings: list[GuardrailFinding] = []
        for claim in claims:
            # Layer 1: rule check.
            if not claim.supporting_evidence_ids:
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.FAIL,
                        severity=GuardrailSeverity.BLOCKER,
                        message=(
                            f"claim {claim.claim_id} has no supporting evidence ids"
                        ),
                        affected_object_type="claim",
                        affected_object_id=claim.claim_id,
                        recommendation="attach at least one evidence id",
                    )
                )
                continue
            for eid in claim.supporting_evidence_ids:
                if eid not in evidence_by_id:
                    findings.append(
                        GuardrailFinding(
                            step_name=step_name,
                            check_name=self.name,
                            status=GuardrailStatus.FAIL,
                            severity=GuardrailSeverity.BLOCKER,
                            message=(
                                f"claim {claim.claim_id} cites missing evidence {eid}"
                            ),
                            affected_object_type="claim",
                            affected_object_id=claim.claim_id,
                            recommendation="add the missing evidence row",
                        )
                    )

            # Layer 2: lexical overlap. We average across the cited
            # evidence rows; a hypothesis claim with a single
            # very-low overlap is allowed but flagged as warning.
            overlaps = [
                lexical_overlap(claim.text, _evidence_text(evidence_by_id[eid]))
                for eid in claim.supporting_evidence_ids
                if eid in evidence_by_id
            ]
            if not overlaps:
                continue
            best = max(overlaps)
            label = grounding_label(best)
            if label == "grounded":
                continue
            if label == "needs_review":
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.NEEDS_REVIEW,
                        severity=GuardrailSeverity.WARNING,
                        message=(
                            f"claim {claim.claim_id} has weak lexical "
                            f"grounding (overlap={best:.2f})"
                        ),
                        affected_object_type="claim",
                        affected_object_id=claim.claim_id,
                    )
                )
            else:
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.NEEDS_REVIEW,
                        severity=GuardrailSeverity.WARNING,
                        message=(
                            f"claim {claim.claim_id} has no lexical overlap "
                            f"with cited evidence (overlap={best:.2f})"
                        ),
                        affected_object_type="claim",
                        affected_object_id=claim.claim_id,
                        recommendation="rewrite the claim or cite different evidence",
                    )
                )
        return findings


__all__ = ["ClaimGroundingValidator"]
