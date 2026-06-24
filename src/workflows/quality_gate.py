"""v16 quality-gated step runner.

``run_step_with_quality_gate`` is the recommended way to wrap a
step function so its output is validated by the
:class:`GuardrailEngine`. The runner is intentionally small so the
existing v15 steps can opt in incrementally.

Usage::

    state = await run_step_with_quality_gate(
        state,
        step=extractor,
        engine=engine,
    )

``step`` is the :class:`WorkflowStep` instance (not its ``run``
method) so the runner can rely on the base class's
``__call__`` to emit v15 ``WorkflowTraceEvent`` rows in addition
to the v16 ``StepEvaluation`` rows.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from src.evaluation.engine import GuardrailEngine
from src.evaluation.models import GuardrailStatus, StepEvaluation
from src.schemas.finrisk import FinRiskWorkflowState
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)


async def run_step_with_quality_gate(
    state: FinRiskWorkflowState,
    *,
    step: WorkflowStep,
    engine: GuardrailEngine,
) -> FinRiskWorkflowState:
    """Run ``step`` and let the engine evaluate pre/post.

    The runner appends a :class:`StepEvaluation` to
    ``state.evaluations`` for every step. The v15 ``WorkflowTraceEvent``
    is emitted by the base class's ``__call__`` so the
    :class:`AgentTimeline` component keeps working unchanged.

    If the step itself raises, the runner catches the exception,
    marks the state as failed, and emits a single BLOCKER finding
    so the workflow trace shows what happened.
    """
    step_name = step.name
    pre_evaluation: StepEvaluation = engine.validate_pre_step(step_name, state)
    if pre_evaluation.status == GuardrailStatus.FAIL and any(
        f.severity.value == "blocker" for f in pre_evaluation.findings
    ):
        logger.info(
            "step %s has pre-step blockers; running anyway", step_name
        )
    started = time.perf_counter()
    try:
        new_state = await step(state)
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("step %s failed", step_name)
        engine.validate_post_step(
            step_name,
            output=None,
            state=state,
        )
        state.status = "failed"
        return state
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    engine.validate_post_step(
        step_name,
        output=new_state,
        state=new_state,
    )
    if new_state.evaluations:
        new_state.evaluations[-1] = new_state.evaluations[-1].model_copy(
            update={"latency_ms": elapsed_ms}
        )
    return new_state


# Backwards-compat alias: tests and older call sites pass a step_fn.
StepFn = Callable[[FinRiskWorkflowState], Awaitable[FinRiskWorkflowState]]


async def run_step_fn_with_quality_gate(
    state: FinRiskWorkflowState,
    *,
    step_name: str,
    step_fn: StepFn,
    engine: GuardrailEngine,
) -> FinRiskWorkflowState:
    """Legacy entry point that takes a raw ``step_fn`` (no trace event)."""
    pre_evaluation: StepEvaluation = engine.validate_pre_step(step_name, state)
    if pre_evaluation.status == GuardrailStatus.FAIL and any(
        f.severity.value == "blocker" for f in pre_evaluation.findings
    ):
        logger.info(
            "step %s has pre-step blockers; running anyway", step_name
        )
    started = time.perf_counter()
    try:
        new_state = await step_fn(state)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("step %s failed", step_name)
        engine.validate_post_step(step_name, output=None, state=state)
        state.status = "failed"
        from src.workflows.state import WorkflowTraceEvent, utcnow

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
    engine.validate_post_step(step_name, output=new_state, state=new_state)
    if new_state.evaluations:
        new_state.evaluations[-1] = new_state.evaluations[-1].model_copy(
            update={"latency_ms": elapsed_ms}
        )
    return new_state


__all__ = [
    "StepFn",
    "run_step_fn_with_quality_gate",
    "run_step_with_quality_gate",
]
