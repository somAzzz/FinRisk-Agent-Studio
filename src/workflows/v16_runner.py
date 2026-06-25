"""v16 runner: wraps the v15 orchestrator and adds the quality layer.

The v16 runner does not change the v15 pipeline. Instead it:

1. Runs the v15 orchestrator and obtains the final state.
2. Instantiates a :class:`GuardrailEngine` with the v16 default
   validator set.
3. Walks the trace and emits a :class:`StepEvaluation` per step
   using the validators' post-step view of the state.
4. Computes the workflow-level evaluation and stores it on
   ``state.workflow_evaluation``.

The runner is intentionally read-only over the v15 result; the v15
``evaluation`` is preserved on the state so existing API tests keep
passing.
"""

from __future__ import annotations

import logging
from typing import Any

from src.evaluation.engine import GuardrailEngine
from src.evaluation.validators import (
    ClaimGroundingValidator,
    EvidenceValidator,
    FinancialSafetyValidator,
    ReportStructureValidator,
    SchemaValidator,
    SourceQualityValidator,
    WorkflowValidator,
)
from src.schemas.finrisk import FinRiskWorkflowState
from src.workflows.finrisk_workflow import run_finrisk_workflow
from src.workflows.state import FinRiskRequest

logger = logging.getLogger(__name__)


def build_default_engine() -> GuardrailEngine:
    """Return an engine pre-loaded with the v16 default validators."""
    return GuardrailEngine(
        validators=[
            SchemaValidator(),
            EvidenceValidator(),
            ClaimGroundingValidator(),
            SourceQualityValidator(),
            FinancialSafetyValidator(),
            ReportStructureValidator(),
            WorkflowValidator(),
        ]
    )


async def run_finrisk_workflow_v16(
    request: FinRiskRequest,
    *,
    engine: GuardrailEngine | None = None,
    fixture_path: Any = None,
    steps: Any = None,
    initial_state: FinRiskWorkflowState | None = None,
) -> FinRiskWorkflowState:
    """Run the v15 workflow and then compute the v16 evaluation.

    v17 alignment: the v16 runner delegates the per-step evaluation
    to ``run_finrisk_workflow(..., quality_gated=True)`` so the
    runtime quality layer is the *primary* mechanism for collecting
    guardrail findings. ``engine.summarize_workflow`` is then called
    to roll the per-step evaluations up into a single
    ``WorkflowEvaluationV16`` that the API can serve.
    """
    engine = engine or build_default_engine()
    state = await run_finrisk_workflow(
        request,
        fixture_path=fixture_path,
        steps=steps,
        initial_state=initial_state,
        quality_engine=engine,
        quality_gated=True,
    )
    # Record a fallback event when running in demo mode (every step
    # was a fixture-backed read). The event helps the v16 demo show
    # the Fallback Events column in the Evaluation tab.
    if request.demo_mode or request.cached_mode:
        from src.evaluation.models import FallbackEvent

        state.fallback_events.append(
            FallbackEvent(
                step_name="market_explorer",
                from_mode="live",
                to_mode="demo",
                reason="demo mode requested by client",
            )
        )
    # If the v15 trace is empty (e.g. the workflow short-circuited
    # before running any step), make sure the engine still records
    # at least the workflow-level invariants.
    if not state.evaluations:
        engine.validate_pre_step("workflow", state)
    state.workflow_evaluation = engine.summarize_workflow(state)
    return state


__all__ = ["build_default_engine", "run_finrisk_workflow_v16"]
