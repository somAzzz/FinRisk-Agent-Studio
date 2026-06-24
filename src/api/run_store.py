"""In-memory run store for FinRisk workflow runs.

This is intentionally simple — production should swap it for SQLite or
Redis. The store is process-local; ``dict`` mutations are atomic in
CPython, so we do not need an explicit lock for the in-memory case.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from src.workflows.state import (
    FinRiskRequest,
    FinRiskWorkflowState,
)


class InMemoryRunStore:
    """Process-local store for ``FinRiskWorkflowState`` instances.

    The store maintains insertion order so ``list_recent`` returns the
    newest runs first. All mutations are synchronous dict updates,
    which are atomic in CPython; production multi-process deployments
    should swap this implementation for SQLite + asyncio lock or Redis.
    """

    def __init__(self) -> None:
        self._states: dict[str, FinRiskWorkflowState] = {}

    async def create(
        self, request: FinRiskRequest
    ) -> FinRiskWorkflowState:
        """Create a new run, store it, and return the initial state."""
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        state = FinRiskWorkflowState(run_id=run_id, request=request)
        self._states[run_id] = state
        return state

    async def get(self, run_id: str) -> FinRiskWorkflowState | None:
        return self._states.get(run_id)

    async def update(self, state: FinRiskWorkflowState) -> None:
        """Replace the stored state for ``state.run_id``."""
        self._states[state.run_id] = state

    async def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]:
        states_list = list(self._states.values())
        # Newest first.
        states_list.reverse()
        return states_list[:limit]

    async def size(self) -> int:
        return len(self._states)


__all__ = ["InMemoryRunStore"]