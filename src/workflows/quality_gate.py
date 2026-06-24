"""v16 quality-gated step runner.

``run_step_with_quality_gate`` is the recommended way to wrap a
step function so its output is validated by the
:class:`GuardrailEngine`. The runner is intentionally small so the
existing v15 steps can opt in incrementally.

Usage::

    state = await run_step_with_quality_gate(
        state,
        step_name="filing_risk_extractor",
        step_fn=extractor.run,
        engine=engine,
    )
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from src.evaluation.engine import GuardrailEngine
from src.evaluation.models import GuardrailStatus, StepEvaluation
from src.schemas.finrisk import FinRiskWorkflowState

logger = logging.getLogger(__name__)

StepFn = Callable[[FinRiskWorkflowState], Awaitable[FinRiskWorkflowState]]


async def run_step_with_quality_gate(
    state: FinRiskWorkflowState,
    *,
    step_name: str,
    step_fn: StepFn,
    engine: GuardrailEngine,
) -> FinRiskWorkflowState:
    """Run ``step_fn`` and let the engine evaluate pre/post.

    The runner appends a :class:`StepEvaluation` to
    ``state.evaluations`` for every step. If the step itself raises,
    the runner catches the exception, marks the state as failed,
    and emits a single BLOCKER finding so the workflow trace
    shows what happened.
    """
    pre_evaluation: StepEvaluation = engine.validate_pre_step(step_name, state)
    if pre_evaluation.status == GuardrailStatus.FAIL and any(
        f.severity.value == "blocker" for f in pre_evaluation.findings
    ):
        # If a blocker already exists we still try to run the step;
        # the step may produce a partial result that helps the user.
        logger.info(
            "step %s has pre-step blockers; running anyway", step_name
        )
    started = time.perf_counter()
    try:
        new_state = await step_fn(state)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("step %s failed", step_name)
        engine.validate_post_step(
            step_name,
            output=None,
            state=state,
        )
        state.status = "failed"
        # Add an error trace event so the v15 trace stays accurate.
        from src.workflows.state import (
            WorkflowTraceEvent,
            utcnow,
        )

        state.trace.append(
            WorkflowTraceEvent(
                step_name=step_name,
                status="failed",
                started_at=utcnow(),
                completed_at=utcnow(),
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        return state
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    engine.validate_post_step(
        step_name,
        output=new_state,
        state=new_state,
    )
    # Carry the latency over for the v16 metrics.
    if new_state.evaluations:
        new_state.evaluations[-1] = new_state.evaluations[-1].model_copy(
            update={"latency_ms": elapsed_ms}
        )
    return new_state


__all__ = ["run_step_with_quality_gate", "StepFn"]
