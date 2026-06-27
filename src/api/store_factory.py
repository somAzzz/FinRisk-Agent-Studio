"""Factory for picking a run-store backend at runtime.

The backend is chosen via the ``RUN_STORE_BACKEND`` env var
(``memory`` | ``sqlite``, default ``memory``). The factory caches
the result so all callers share one instance per process.

There are two typed factories:

- :func:`get_run_store` returns a backend specialised for
  :class:`FinRiskWorkflowState` (used by the FinRisk workflow
  routes).
- :func:`get_supply_chain_store` returns a backend specialised
  for :class:`SupplyChainExploreState` (used by the v18 supply-
  chain routes).

For the FinRisk workflow store, see :mod:`src.api.run_store`.
"""

from __future__ import annotations

import os
from functools import lru_cache

from src.api.run_store import (
    FinRiskInMemoryRunStore,
    FinRiskSQLiteRunStore,
    InMemoryRunStore,
    RunStoreBackend,
    SQLiteRunStore,
    TypedSQLiteRunStore,
)
from src.supply_chain.models import SupplyChainExploreState


def _build_finrisk_backend():
    backend = os.environ.get("RUN_STORE_BACKEND", "memory").lower()
    if backend == "memory":
        return FinRiskInMemoryRunStore()
    if backend == "sqlite":
        db_path = os.environ.get("RUN_STORE_DB", ".cache/fintext_llm/runs.sqlite3")
        return FinRiskSQLiteRunStore(db_path)
    raise ValueError(
        f"Unknown RUN_STORE_BACKEND={backend!r}. Expected 'memory' or 'sqlite'."
    )


def _build_supply_chain_backend() -> RunStoreBackend[SupplyChainExploreState]:
    """Build the supply-chain backend using the same env knob as FinRisk."""
    backend = os.environ.get("RUN_STORE_BACKEND", "memory").lower()
    if backend == "memory":
        return InMemoryRunStore[SupplyChainExploreState]()
    if backend == "sqlite":
        db_path = os.environ.get("RUN_STORE_DB", ".cache/fintext_llm/runs.sqlite3")
        return TypedSQLiteRunStore(
            db_path,
            model=SupplyChainExploreState,
            table="supply_chain_runs",
        )
    raise ValueError(
        f"Unknown RUN_STORE_BACKEND={backend!r}. Expected 'memory' or 'sqlite'."
    )


@lru_cache(maxsize=1)
def get_run_store() -> RunStoreBackend:
    """Return the process-wide FinRisk run-store backend."""
    return _build_finrisk_backend()


@lru_cache(maxsize=1)
def get_supply_chain_store() -> RunStoreBackend[SupplyChainExploreState]:
    """Return the process-wide supply-chain run-store backend."""
    return _build_supply_chain_backend()


def reset_run_store_for_tests() -> None:
    """Drop both cached backends. Test-only helper."""
    get_run_store.cache_clear()
    get_supply_chain_store.cache_clear()


__all__ = [
    "SQLiteRunStore",
    "get_run_store",
    "get_supply_chain_store",
    "reset_run_store_for_tests",
]
