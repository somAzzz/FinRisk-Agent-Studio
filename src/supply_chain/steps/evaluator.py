"""v18 Step 7: supply chain evaluator."""

from __future__ import annotations

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.sankey import evaluate_state
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainEvaluatorStep(SupplyChainStep):
    """Compute the workflow-level :class:`SupplyChainEvaluation`."""

    name = "supply_chain_evaluator"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if state.sankey is None:
            state.warnings.append("evaluator: sankey not built yet")
            return state
        state.evaluation = evaluate_state(state, state.sankey)
        # Mirror the v15/v17 pattern: workflow status follows the
        # evaluation verdict.
        verdict = state.evaluation.final_status
        if verdict == "failed":
            state.status = "failed"
        elif verdict == "needs_review":
            state.status = "needs_review"
        else:
            state.status = "completed"
        return state


__all__ = ["SupplyChainEvaluatorStep"]
