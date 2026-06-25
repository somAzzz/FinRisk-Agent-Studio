"""Base class for v18 supply chain workflow steps.

Mirrors the v15 ``WorkflowStep`` base so the v18 orchestrator can
emit per-step trace events and let the v17 quality gate wrap the
state mutations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.supply_chain.models import (
    SupplyChainExploreState,
    SupplyChainTraceEvent,
)
from src.workflows.state import utcnow

logger = logging.getLogger(__name__)


class SupplyChainStep:
    """Base class for v18 supply chain workflow steps."""

    name: str = "step"

    def __init__(self, *, critical: bool = False) -> None:
        self.critical = critical

    async def run(self, state: SupplyChainExploreState) -> SupplyChainExploreState:
        raise NotImplementedError

    async def __call__(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        event = SupplyChainTraceEvent(
            step_name=self.name,
            status="running",
            started_at=utcnow(),
            input_summary={
                "node_count": len(state.nodes),
                "link_count": len(state.links),
                "evidence_count": len(state.evidence),
                "status": state.status,
            },
        )
        state.trace.append(event)
        started = time.perf_counter()
        try:
            new_state = await self.run(state)
        except Exception as exc:
            event.status = "failed"
            event.completed_at = utcnow()
            event.duration_ms = int((time.perf_counter() - started) * 1000)
            event.error = f"{type(exc).__name__}: {exc}"
            logger.warning("step %s failed: %s", self.name, exc)
            if self.critical:
                new_state = state.model_copy(update={"status": "failed"})
            else:
                new_state = state
            return new_state
        event.status = "completed"
        event.completed_at = utcnow()
        event.duration_ms = int((time.perf_counter() - started) * 1000)
        event.output_summary = {
            "node_count": len(new_state.nodes),
            "link_count": len(new_state.links),
            "evidence_count": len(new_state.evidence),
            "status": new_state.status,
        }
        return new_state


__all__ = ["SupplyChainStep"]


# ``Any`` is imported above so future steps can keep their
# annotations light without losing the v17 quality-gate contract.
_ = Any
