"""Process-wide message-store and recorder factories."""

from __future__ import annotations

import functools
import os
from pathlib import Path

from src.ai.approvals import DeferredApprovalStore, SQLiteDeferredApprovalStore
from src.ai.message_store import (
    AgentMessageStore,
    InMemoryAgentMessageStore,
    SQLiteAgentMessageStore,
)
from src.ai.recorder import AgentRunRecorder


@functools.lru_cache(maxsize=1)
def get_agent_message_store() -> AgentMessageStore:
    """Use the configured run-store durability without changing legacy tables."""
    backend = os.environ.get("RUN_STORE_BACKEND", "memory").strip().lower()
    if backend == "sqlite":
        path = Path(
            os.environ.get(
                "RUN_STORE_DB", ".cache/finrisk_agent_studio/runs.sqlite3"
            )
        )
        return SQLiteAgentMessageStore(path)
    if backend != "memory":
        raise ValueError(f"unsupported RUN_STORE_BACKEND {backend!r}")
    return InMemoryAgentMessageStore()


@functools.lru_cache(maxsize=1)
def get_agent_run_recorder() -> AgentRunRecorder:
    """Return the process-wide idempotent Agent recorder."""
    return AgentRunRecorder(get_agent_message_store())


@functools.lru_cache(maxsize=1)
def get_deferred_approval_store() -> DeferredApprovalStore:
    """Return an approval store with the same durability as run state."""
    backend = os.environ.get("RUN_STORE_BACKEND", "memory").strip().lower()
    if backend == "sqlite":
        path = Path(
            os.environ.get(
                "RUN_STORE_DB", ".cache/finrisk_agent_studio/runs.sqlite3"
            )
        )
        return SQLiteDeferredApprovalStore(path)
    if backend != "memory":
        raise ValueError(f"unsupported RUN_STORE_BACKEND {backend!r}")
    return DeferredApprovalStore()


def reset_agent_message_store_for_tests() -> None:
    """Clear only factory instances; individual test stores own their data."""
    get_agent_run_recorder.cache_clear()
    get_agent_message_store.cache_clear()
    get_deferred_approval_store.cache_clear()


__all__ = [
    "get_agent_message_store",
    "get_agent_run_recorder",
    "get_deferred_approval_store",
    "reset_agent_message_store_for_tests",
]
