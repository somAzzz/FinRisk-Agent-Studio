"""Run-store backends for FinRisk workflow runs.

Defines a :class:`RunStoreBackend` :class:`typing.Protocol` plus
two implementations:

- :class:`InMemoryRunStore` — the original process-local dict store.
- :class:`SQLiteRunStore` — a durable, single-file backend backed by
  stdlib :mod:`sqlite3`. Suitable for single-process and
  single-machine deployments; a multi-process deployment should
  swap this for Postgres / Redis.

The factory in :mod:`src.api.store_factory` picks the backend at
runtime from the ``RUN_STORE_BACKEND`` env var (``memory`` |
``sqlite``, default ``memory``).
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.workflows.state import (
    FinRiskRequest,
    FinRiskWorkflowState,
)


@runtime_checkable
class RunStoreBackend(Protocol):
    """The minimal contract that workflow route handlers depend on."""

    async def create(
        self, request: FinRiskRequest
    ) -> FinRiskWorkflowState: ...

    async def get(self, run_id: str) -> FinRiskWorkflowState | None: ...

    async def update(self, state: FinRiskWorkflowState) -> None: ...

    async def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]: ...

    async def size(self) -> int: ...

    async def clear(self) -> None:
        """Drop every run. Test-only / admin helper."""
        ...


class InMemoryRunStore:
    """Process-local store for ``FinRiskWorkflowState`` instances.

    The store maintains insertion order so ``list_recent`` returns
    the newest runs first. All mutations are synchronous dict
    updates, which are atomic in CPython; production multi-process
    deployments should swap this implementation for SQLite +
    asyncio lock or Redis.
    """

    def __init__(self) -> None:
        self._states: dict[str, FinRiskWorkflowState] = {}

    async def create(self, request: FinRiskRequest) -> FinRiskWorkflowState:
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
        states_list.reverse()
        return states_list[:limit]

    async def size(self) -> int:
        return len(self._states)

    async def clear(self) -> None:
        """Drop every run."""
        self._states.clear()


class SQLiteRunStore:
    """Durable, single-file ``sqlite3``-backed run store.

    State is serialized with Pydantic's ``model_dump`` /
    ``model_validate`` round-trip so any Pydantic-aware field on
    :class:`FinRiskWorkflowState` round-trips correctly. The
    connection is opened lazily and held per-instance; concurrent
    asyncio tasks are serialized through ``asyncio.to_thread`` to
    keep the stdlib ``sqlite3`` module happy in an async context.

    Multi-writer concurrency is limited — the underlying
    ``sqlite3.Connection`` serializes writes. For multi-process
    deployments use Postgres / Redis instead.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        return conn

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
            self._initialized = True
        return self._conn

    def _row_to_state(self, row: tuple[Any, ...]) -> FinRiskWorkflowState:
        payload = row[0]
        return FinRiskWorkflowState.model_validate_json(payload)

    def _sync_create(self, request_payload: str) -> str:
        """Persist a fresh state built from a request payload.

        ``request_payload`` is a JSON-serialized ``FinRiskRequest``
        (not a full state). We rebuild a real :class:`FinRiskWorkflowState`
        from it, assign the new ``run_id``, and persist.
        """
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        request = FinRiskRequest.model_validate_json(request_payload)
        state = FinRiskWorkflowState(run_id=run_id, request=request)
        payload = state.model_dump_json()
        conn = self._ensure()
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, payload, created_at) VALUES (?, ?, ?)",
            (run_id, payload, _now()),
        )
        return run_id

    def _sync_get(self, run_id: str) -> FinRiskWorkflowState | None:
        conn = self._ensure()
        row = conn.execute(
            "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row)

    def _sync_update(self, state: FinRiskWorkflowState) -> None:
        conn = self._ensure()
        payload = state.model_dump_json()
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, payload, created_at) VALUES (?, ?, ?)",
            (state.run_id, payload, _now()),
        )

    def _sync_list_recent(self, limit: int) -> list[FinRiskWorkflowState]:
        conn = self._ensure()
        rows = conn.execute(
            "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_state(r) for r in rows]

    def _sync_size(self) -> int:
        conn = self._ensure()
        row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(row[0]) if row else 0

    def _sync_clear(self) -> None:
        conn = self._ensure()
        conn.execute("DELETE FROM runs")

    async def create(self, request: FinRiskRequest) -> FinRiskWorkflowState:
        request_payload = request.model_dump_json()
        async with self._lock:
            run_id = await asyncio.to_thread(self._sync_create, request_payload)
        result = await self.get(run_id)
        assert result is not None
        return result

    async def get(self, run_id: str) -> FinRiskWorkflowState | None:
        async with self._lock:
            return await asyncio.to_thread(self._sync_get, run_id)

    async def update(self, state: FinRiskWorkflowState) -> None:
        async with self._lock:
            await asyncio.to_thread(self._sync_update, state)

    async def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]:
        async with self._lock:
            return await asyncio.to_thread(self._sync_list_recent, limit)

    async def size(self) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._sync_size)

    async def clear(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._sync_clear)

    async def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._initialized = False


def _now() -> float:
    """Monotonic-ish clock used for ordering."""
    import time

    return time.time()


# Re-export for backwards-compat with the original module surface.
__all__ = [
    "InMemoryRunStore",
    "RunStoreBackend",
    "SQLiteRunStore",
]
