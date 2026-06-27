"""Run-store backends for FinRisk workflow runs.

Defines a generic :class:`RunStoreBackend` :class:`typing.Protocol`
parameterized over the state type, plus two implementations:

- :class:`InMemoryRunStore` — the original process-local dict store.
- :class:`SQLiteRunStore` — a durable, single-file backend backed by
  stdlib :mod:`sqlite3`. Suitable for single-process and
  single-machine deployments; a multi-process deployment should
  swap this for Postgres / Redis.

The factory in :mod:`src.api.store_factory` picks the backend at
runtime from the ``RUN_STORE_BACKEND`` env var (``memory`` |
``sqlite``, default ``memory``). A separate
:func:`get_supply_chain_store` factory returns a backend specialised
for ``SupplyChainExploreState`` so the supply-chain routes share
the same persistence machinery.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from src.workflows.state import (
    FinRiskRequest,
    FinRiskWorkflowState,
)

T = TypeVar("T")


@runtime_checkable
class RunStoreBackend[T](Protocol):
    """The minimal contract that route handlers depend on.

    A concrete backend is keyed by a string ``run_id`` and stores
    Pydantic state objects. ``create`` is supplied only by the
    FinRisk workflow backend (the supply-chain backend mints its
    own run ids inside the workflow and only needs ``update`` /
    ``get`` / ``clear``); supply-chain implementations may
    implement ``create`` by raising :class:`NotImplementedError`.
    """

    async def get(self, run_id: str) -> T | None: ...

    async def update(self, state: T) -> None: ...

    async def size(self) -> int: ...

    async def clear(self) -> None:
        """Drop every run. Test-only / admin helper."""
        ...


class InMemoryRunStore(RunStoreBackend[T]):
    """Process-local store for state objects keyed by ``run_id``.

    Maintains insertion order so :meth:`list_recent` returns the
    newest runs first. All mutations are synchronous dict updates,
    which are atomic in CPython; production multi-process
    deployments should swap this for SQLite + asyncio lock or
    Redis.
    """

    def __init__(self) -> None:
        self._states: dict[str, T] = {}

    async def get(self, run_id: str) -> T | None:
        return self._states.get(run_id)

    async def update(self, state: T) -> None:
        """Replace the stored state for ``state.run_id``."""
        self._states[state.run_id] = state  # type: ignore[attr-defined]

    async def list_recent(self, limit: int = 20) -> list[T]:
        states_list = list(self._states.values())
        states_list.reverse()
        return states_list[:limit]

    async def size(self) -> int:
        return len(self._states)

    async def clear(self) -> None:
        self._states.clear()


class SQLiteRunStore(RunStoreBackend[T]):
    """Durable, single-file ``sqlite3``-backed run store.

    State is serialized with Pydantic's ``model_dump_json`` /
    ``model_validate_json`` round-trip so any Pydantic-aware field
    round-trips correctly. The connection is opened lazily and
    held per-instance; concurrent asyncio tasks are serialized
    through ``asyncio.to_thread`` to keep stdlib ``sqlite3`` happy
    in an async context.

    Multi-writer concurrency is limited — the underlying
    ``sqlite3.Connection`` serializes writes. For multi-process
    deployments use Postgres / Redis instead.
    """

    def __init__(self, db_path: str | Path, *, table: str = "runs") -> None:
        self._db_path = Path(db_path)
        self._table = table
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Public async methods run sqlite work in a thread-pool via
        # ``asyncio.to_thread``. The instance lock serializes access,
        # while this flag allows the held connection to be reused by
        # whichever worker thread handles the next operation.
        conn = sqlite3.connect(
            self._db_path,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
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
        return self._conn

    def _row_to_state(self, row: tuple[Any, ...], model: type[T]) -> T:
        return model.model_validate_json(row[0])

    def _sync_update(self, state: T) -> None:
        conn = self._ensure()
        payload = state.model_dump_json()  # type: ignore[attr-defined]
        conn.execute(
            f"INSERT OR REPLACE INTO {self._table}(run_id, payload, created_at) "
            "VALUES (?, ?, ?)",
            (state.run_id, payload, _now()),  # type: ignore[attr-defined]
        )

    def _sync_get(self, run_id: str, model: type[T]) -> T | None:
        conn = self._ensure()
        row = conn.execute(
            f"SELECT payload FROM {self._table} WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row, model)

    def _sync_size(self) -> int:
        conn = self._ensure()
        row = conn.execute(f"SELECT COUNT(*) FROM {self._table}").fetchone()
        return int(row[0]) if row else 0

    def _sync_list_recent(self, limit: int, model: type[T]) -> list[T]:
        conn = self._ensure()
        rows = conn.execute(
            f"SELECT payload FROM {self._table} ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_state(r, model) for r in rows]

    def _sync_clear(self) -> None:
        conn = self._ensure()
        conn.execute(f"DELETE FROM {self._table}")

    async def get(self, run_id: str, model: type[T] | None = None) -> T | None:
        if model is None:
            raise ValueError(
                "SQLiteRunStore.get requires an explicit `model=` "
                "argument because it is generic."
            )
        async with self._lock:
            return await asyncio.to_thread(self._sync_get, run_id, model)

    async def update(self, state: T) -> None:
        async with self._lock:
            await asyncio.to_thread(self._sync_update, state)

    async def list_recent(self, limit: int = 20) -> list[T]:
        # ``model`` is intentionally not part of the public API; the
        # FinRisk-typed subclass passes it for us.
        raise NotImplementedError(
            "SQLiteRunStore is generic; use the FinRiskSQLiteRunStore "
            "subclass or pass a typed helper."
        )

    async def _list_recent_typed(self, limit: int, model: type[T]) -> list[T]:
        async with self._lock:
            return await asyncio.to_thread(self._sync_list_recent, limit, model)

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


# ---------------------------------------------------------------------------
# FinRisk-typed helpers (kept here so the rest of the codebase has a
# single import surface for the workflow store).
# ---------------------------------------------------------------------------


class FinRiskInMemoryRunStore(InMemoryRunStore[FinRiskWorkflowState]):
    """In-memory backend specialised for ``FinRiskWorkflowState``."""

    async def create(self, request: FinRiskRequest) -> FinRiskWorkflowState:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        state = FinRiskWorkflowState(run_id=run_id, request=request)
        self._states[run_id] = state
        return state


class FinRiskSQLiteRunStore(SQLiteRunStore[FinRiskWorkflowState]):
    """SQLite backend specialised for ``FinRiskWorkflowState``."""

    async def create(self, request: FinRiskRequest) -> FinRiskWorkflowState:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        state = FinRiskWorkflowState(run_id=run_id, request=request)
        await self.update(state)
        return state

    async def get(self, run_id: str) -> FinRiskWorkflowState | None:
        return await super().get(run_id, FinRiskWorkflowState)

    async def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]:
        return await self._list_recent_typed(limit, FinRiskWorkflowState)


class TypedSQLiteRunStore(SQLiteRunStore[T]):
    """SQLite backend for state types that do not need a ``create`` helper."""

    def __init__(self, db_path: str | Path, *, model: type[T], table: str) -> None:
        super().__init__(db_path, table=table)
        self._model = model

    async def get(self, run_id: str) -> T | None:
        return await super().get(run_id, self._model)

    async def list_recent(self, limit: int = 20) -> list[T]:
        return await self._list_recent_typed(limit, self._model)


def _now() -> float:
    import time

    return time.time()


# Backwards-compat alias for code that still imports ``InMemoryRunStore``
# expecting the original FinRisk-typed class.
InMemoryRunStoreForFinRisk = FinRiskInMemoryRunStore


__all__ = [
    "FinRiskInMemoryRunStore",
    "FinRiskSQLiteRunStore",
    "InMemoryRunStore",
    "RunStoreBackend",
    "SQLiteRunStore",
    "TypedSQLiteRunStore",
]
