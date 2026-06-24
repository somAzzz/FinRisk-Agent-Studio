"""Step 8: workflow evaluator / guardrails.

A thin wrapper around :func:`src.workflows.evaluation.evaluate_workflow_state`
that maps the verdict onto ``state.status``. The actual rules live in the
shared module so the offline eval runner can reuse them.
"""

from __future__ import annotations

from src.workflows.evaluation import evaluate_workflow_state
from src.workflows.state import FinRiskWorkflowState
from src.workflows.steps._base import WorkflowStep


class EvaluatorStep(WorkflowStep):
    """Run guardrails on the generated report and emit a ``WorkflowEvaluation``."""

    name = "evaluator"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        state.evaluation = evaluate_workflow_state(state)
        verdict = state.evaluation.final_status
        if verdict == "pass":
            state.status = "completed"
        elif verdict == "needs_review":
            state.status = "needs_review"
        else:
            state.status = "failed"
        return state


__all__ = ["EvaluatorStep"]
