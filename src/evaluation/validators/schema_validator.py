"""Schema validator: every step output must be a Pydantic BaseModel."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.workflows.state import FinRiskWorkflowState


class SchemaValidator:
    """Verify that ``output`` is a valid Pydantic model.

    The check is shallow — we ask Pydantic to re-validate the model
    (which runs the model's own validators) and surface any
    :class:`ValidationError` as a BLOCKER finding. Step output types
    are intentionally not declared in the protocol because every
    step uses a different Pydantic model.
    """

    name = "schema"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        if output is None:
            return [
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=f"{step_name} produced no output",
                    affected_object_type="workflow",
                )
            ]
        if isinstance(output, BaseModel):
            try:
                # model_validate is the most thorough re-validation:
                # it walks the model tree and runs field validators.
                # Using ``type(output)`` keeps the call type-safe.
                output.__class__.model_validate(output.model_dump())
            except ValidationError as exc:
                return [
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.FAIL,
                        severity=GuardrailSeverity.BLOCKER,
                        message=f"schema validation failed: {exc.errors()[0]['msg']}",
                        affected_object_type="workflow",
                    )
                ]
            return []
        return [
            GuardrailFinding(
                step_name=step_name,
                check_name=self.name,
                status=GuardrailStatus.FAIL,
                severity=GuardrailSeverity.BLOCKER,
                message=f"{step_name} output is not a Pydantic model",
                affected_object_type="workflow",
            )
        ]


__all__ = ["SchemaValidator"]
