"""Factory for picking a run-store backend at runtime.

The backend is chosen via the ``RUN_STORE_BACKEND`` env var
(``memory`` | ``sqlite``, default ``memory``). The factory caches
the result so all callers share one instance per process.

For the FinRisk workflow store, see :mod:`src.api.run_store`.
"""

from __future__ import annotations

import os
from functools import lru_cache

from src.api.run_store import InMemoryRunStore, RunStoreBackend, SQLiteRunStore


@lru_cache(maxsize=1)
def get_run_store() -> RunStoreBackend:
    """Return the process-wide run-store backend."""
    backend = os.environ.get("RUN_STORE_BACKEND", "memory").lower()
    if backend == "memory":
        return InMemoryRunStore()
    if backend == "sqlite":
        db_path = os.environ.get("RUN_STORE_DB", ".cache/fintext_llm/runs.sqlite3")
        return SQLiteRunStore(db_path)
    raise ValueError(
        f"Unknown RUN_STORE_BACKEND={backend!r}. Expected 'memory' or 'sqlite'."
    )


def reset_run_store_for_tests() -> None:
    """Drop the cached backend. Test-only helper."""
    get_run_store.cache_clear()


__all__ = ["get_run_store", "reset_run_store_for_tests"]
