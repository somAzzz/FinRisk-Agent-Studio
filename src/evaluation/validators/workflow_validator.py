"""Workflow validator: invariants that span the entire state.

The validator checks a small set of properties that do not belong to
a single step:

- ``state.run_id`` is non-empty.
- ``state.request`` is present.
- the trace contains at least one ``completed`` event when
  ``status == "completed"``.
- fallback events are recorded when expected (e.g. demo mode is
  always offline so a fallback event is acceptable but not required).
"""

from __future__ import annotations

from typing import Any

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.schemas.finrisk import FinRiskWorkflowState


class WorkflowValidator:
    name = "workflow"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        findings: list[GuardrailFinding] = []
        if not state.run_id:
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message="state.run_id is empty",
                    affected_object_type="workflow",
                )
            )
        if state.request is None:
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message="state.request is missing",
                    affected_object_type="workflow",
                )
            )
        if state.status == "completed" and not any(
            event.status == "completed" for event in state.trace
        ):
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.NEEDS_REVIEW,
                    severity=GuardrailSeverity.WARNING,
                    message="status is completed but trace has no completed events",
                    affected_object_type="workflow",
                )
            )
        return findings


__all__ = ["WorkflowValidator"]
