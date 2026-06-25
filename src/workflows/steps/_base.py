"""Shared base for workflow steps.

The :class:`WorkflowStep` base class centralizes trace event creation so
every concrete step gets the same status transition rules without
duplicating boilerplate.
"""

from __future__ import annotations

import logging
from typing import Any

from src.workflows.state import (
    FinRiskWorkflowState,
    WorkflowTraceEvent,
    utcnow,
)

logger = logging.getLogger(__name__)


class WorkflowStep:
    """Base class for FinRisk workflow steps.

    Concrete subclasses must set ``name`` and implement ``async run``.
    On entry the base emits a ``running`` trace event; on exit it
    transitions to ``completed`` / ``failed`` / ``skipped`` and writes
    the timestamps + output summary.
    """

    name: str = "step"

    def __init__(self, *, critical: bool = False) -> None:
        # ``critical=True`` means a failure should abort the workflow;
        # default best-effort steps record the error but keep going.
        self.critical = critical

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        raise NotImplementedError

    async def __call__(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        event = WorkflowTraceEvent(
            step_name=self.name,
            status="running",
            started_at=utcnow(),
            input_summary=_summarize(state.request.model_dump()),
        )
        state.trace.append(event)
        try:
            state = await self.run(state)
        except Exception as exc:
            event.status = "failed"
            event.completed_at = utcnow()
            event.error = f"{type(exc).__name__}: {exc}"
            logger.warning("step %s failed: %s", self.name, exc)
            if self.critical:
                state.status = "failed"
            return state
        event.status = "completed"
        event.completed_at = utcnow()
        event.output_summary = _summarize(_step_output(state, self.name))
        return state


def _summarize(payload: Any, limit: int = 240) -> str:
    """Compact string summary of arbitrary payload for trace events."""
    if payload is None:
        return ""
    text = str(payload)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _step_output(state: FinRiskWorkflowState, step_name: str) -> Any:
    """Return the field on ``state`` most recently populated by ``step_name``.

    Best-effort heuristic: we look at a fixed mapping so trace summaries
    stay readable. Unknown steps fall back to the request.
    """
    mapping: dict[str, str] = {
        "company_resolver": "company",
        "filing_risk_extractor": "filing_risks",
        "market_explorer": "market_evidence",
        "evidence_normalizer": "normalized_evidence",
        "risk_scorer": "risk_scores",
        "lifecycle_classifier": "risk_lifecycles",
        "graph_reasoner": "graph_insights",
        "report_generator": "report",
        "evaluator": "evaluation",
    }
    field = mapping.get(step_name)
    if field is None:
        return None
    value = getattr(state, field, None)
    if value is None:
        return None
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    return str(type(value).__name__)


__all__ = ["WorkflowStep", "_step_output", "_summarize"]