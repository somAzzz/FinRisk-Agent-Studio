"""Agent protocols that every concrete agent must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.agents.state import AgentState


@runtime_checkable
class Agent(Protocol):
    """Synchronous agent contract.

    Implementations receive an :class:`AgentState`, mutate or extend it, and
    return the (possibly updated) state. Implementations should be pure with
    respect to side effects other than the state they return.
    """

    name: str

    def run(self, state: AgentState) -> AgentState:
        """Execute a single agent step and return the updated state."""
        ...


@runtime_checkable
class AsyncAgent(Protocol):
    """Asynchronous counterpart to :class:`Agent`."""

    name: str

    async def run(self, state: AgentState) -> AgentState:
        """Execute a single agent step and return the updated state."""
        ...
