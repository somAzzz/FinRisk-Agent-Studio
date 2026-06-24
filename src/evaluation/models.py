"""v16 quality-layer models.

These types are the richer replacement for the v15
``WorkflowEvaluation`` shape. The v15 flat model is still produced
by the existing ``EvaluatorStep`` for backward compatibility; the
v16 layer augments the workflow state with :class:`StepEvaluation`
records (one per step) and a :class:`WorkflowEvaluation` that
aggregates them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.workflows.state import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GuardrailSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class GuardrailStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


AffectedObjectType = Literal[
    "risk",
    "evidence",
    "claim",
    "source",
    "graph_path",
    "report_section",
    "workflow",
]


class GuardrailFinding(BaseModel):
    """A single guardrail observation.

    The model is intentionally flat: it carries everything a UI drawer
    needs (severity, recommendation, affected object id) without
    requiring callers to traverse a tree.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(default_factory=lambda: f"f-{uuid.uuid4().hex[:8]}")
    step_name: str
    check_name: str
    status: GuardrailStatus
    severity: GuardrailSeverity
    message: str
    affected_object_type: AffectedObjectType
    affected_object_id: str | None = None
    recommendation: str | None = None


# ---------------------------------------------------------------------------
# Per-step evaluation
# ---------------------------------------------------------------------------


class StepEvaluation(BaseModel):
    """The aggregated guardrail record for a single workflow step."""

    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: GuardrailStatus
    findings: list[GuardrailFinding] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    latency_ms: int | None = None
    fallback_used: str | None = None


# ---------------------------------------------------------------------------
# Workflow-level evaluation
# ---------------------------------------------------------------------------


class WorkflowEvaluationV16(BaseModel):
    """v16 workflow-level evaluation.

    Aggregates all :class:`StepEvaluation` rows into a single
    verdict. ``final_status`` collapses to PASS when no warning or
    blocker is present, NEEDS_REVIEW when only warnings exist, and
    FAIL when one or more blockers are recorded.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    final_status: GuardrailStatus
    step_evaluations: list[StepEvaluation] = Field(default_factory=list)
    overall_metrics: dict[str, float] = Field(default_factory=dict)
    blocker_count: int = 0
    warning_count: int = 0
    unsupported_claims: list[str] = Field(default_factory=list)
    human_review_required: bool = False


# ---------------------------------------------------------------------------
# Fallback event
# ---------------------------------------------------------------------------


class FallbackEvent(BaseModel):
    """A single fallback taken during the workflow run."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"fb-{uuid.uuid4().hex[:8]}")
    step_name: str
    from_mode: str
    to_mode: str
    reason: str
    occurred_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def aggregate_status(step_evaluations: list[StepEvaluation]) -> GuardrailStatus:
    """Collapse per-step statuses into a single verdict."""
    statuses = {step.status for step in step_evaluations}
    if GuardrailStatus.FAIL in statuses:
        return GuardrailStatus.FAIL
    if GuardrailStatus.WARNING in statuses or GuardrailStatus.NEEDS_REVIEW in statuses:
        return GuardrailStatus.NEEDS_REVIEW
    if not statuses:
        return GuardrailStatus.PASS
    return GuardrailStatus.PASS


def counts(step_evaluations: list[StepEvaluation]) -> tuple[int, int]:
    blockers = sum(
        1
        for s in step_evaluations
        for f in s.findings
        if f.severity == GuardrailSeverity.BLOCKER
    )
    warnings = sum(
        1
        for s in step_evaluations
        for f in s.findings
        if f.severity == GuardrailSeverity.WARNING
    )
    return blockers, warnings


def build_workflow_evaluation(
    *,
    run_id: str,
    step_evaluations: list[StepEvaluation],
    overall_metrics: dict[str, float] | None = None,
    unsupported_claims: list[str] | None = None,
) -> WorkflowEvaluationV16:
    """Compose a :class:`WorkflowEvaluationV16` from a list of step evals."""
    final = aggregate_status(step_evaluations)
    blockers, warnings = counts(step_evaluations)
    return WorkflowEvaluationV16(
        run_id=run_id,
        final_status=final,
        step_evaluations=step_evaluations,
        overall_metrics=overall_metrics or {},
        blocker_count=blockers,
        warning_count=warnings,
        unsupported_claims=list(unsupported_claims or []),
        human_review_required=final != GuardrailStatus.PASS,
    )


__all__ = [
    "GuardrailSeverity",
    "GuardrailStatus",
    "GuardrailFinding",
    "StepEvaluation",
    "WorkflowEvaluationV16",
    "FallbackEvent",
    "aggregate_status",
    "counts",
    "build_workflow_evaluation",
]
