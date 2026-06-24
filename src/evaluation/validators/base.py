"""Base protocol for v16 validators.

Validators inspect a step's output and emit zero or more
:class:`GuardrailFinding` records. The contract is deliberately
narrow: a single async ``validate`` method, a stable ``name`` for
logging, and a no-raise guarantee so the engine can wrap a
:class:`GuardrailFinding` around any internal exception.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.workflows.state import FinRiskWorkflowState


# Short aliases used in import sites.
Finding = GuardrailFinding
FindingStatus = GuardrailStatus
FindingSeverity = GuardrailSeverity


@runtime_checkable
class Validator(Protocol):
    """Protocol every v16 guardrail validator implements.

    Concrete validators are typically simple Python classes
    (no inheritance required). The engine does an ``isinstance``-free
    duck-typed call: it just expects ``name`` and ``validate``.
    """

    name: str

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        ...


__all__ = ["Validator", "Finding", "FindingStatus", "FindingSeverity"]
