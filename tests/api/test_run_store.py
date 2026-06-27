"""Tests for the new run-store backend factory and SQLite implementation.

These tests exercise the factory in :mod:`src.api.store_factory`
plus the :class:`SQLiteRunStore` durability contract. The InMemory
backend is covered by the existing ``tests/api/test_workflow_api.py``
suite (no changes required).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.run_store import (
    FinRiskInMemoryRunStore,
    FinRiskSQLiteRunStore,
)
from src.api.store_factory import (
    get_run_store,
    get_supply_chain_store,
    reset_run_store_for_tests,
)
from src.schemas.finrisk import FinRiskRequest
from src.supply_chain.models import SupplyChainExploreRequest, SupplyChainExploreState


@pytest.fixture(autouse=True)
def _reset_factory() -> None:
    reset_run_store_for_tests()
    yield
    reset_run_store_for_tests()


def test_factory_defaults_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_STORE_BACKEND", raising=False)
    store = get_run_store()
    assert isinstance(store, FinRiskInMemoryRunStore)


def test_factory_supports_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("RUN_STORE_DB", ":memory:")
    store = get_run_store()
    assert isinstance(store, FinRiskSQLiteRunStore)


def test_supply_chain_factory_supports_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("RUN_STORE_DB", ":memory:")
    store = get_supply_chain_store()
    state = SupplyChainExploreState(
        run_id="sc-run-test",
        request=SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        ),
    )
    asyncio_run(store.update(state))
    loaded = asyncio_run(store.get("sc-run-test"))
    assert loaded is not None
    assert loaded.run_id == "sc-run-test"
    assert loaded.request.product_name == "ChatGPT"


def test_factory_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_STORE_BACKEND", "mongodb")
    with pytest.raises(ValueError, match="Unknown RUN_STORE_BACKEND"):
        get_run_store()


def test_sqlite_round_trip(tmp_path: Path) -> None:
    """A state written by one instance can be read by another on the same file."""
    db = tmp_path / "runs.sqlite3"
    store_a = FinRiskSQLiteRunStore(db)
    request = FinRiskRequest.model_validate(
        {"ticker": "AAPL", "analysis_goal": "Identify risks.", "demo_mode": True}
    )

    state = asyncio_run(store_a.create(request))
    assert state.run_id.startswith("run-")
    assert state.request.ticker == "AAPL"

    # Mutate and persist.
    state.status = "completed"
    asyncio_run(store_a.update(state))

    # New instance against the same file sees the update.
    store_b = FinRiskSQLiteRunStore(db)
    loaded = asyncio_run(store_b.get(state.run_id))
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.run_id == state.run_id


def test_sqlite_size_and_clear(tmp_path: Path) -> None:
    db = tmp_path / "runs.sqlite3"
    store = FinRiskSQLiteRunStore(db)
    request = FinRiskRequest.model_validate(
        {"ticker": "MSFT", "analysis_goal": "Identify risks.", "demo_mode": True}
    )
    asyncio_run(store.create(request))
    asyncio_run(store.create(request))
    assert asyncio_run(store.size()) == 2
    asyncio_run(store.clear())
    assert asyncio_run(store.size()) == 0


def test_sqlite_list_recent_ordering(tmp_path: Path) -> None:
    db = tmp_path / "runs.sqlite3"
    store = FinRiskSQLiteRunStore(db)
    request = FinRiskRequest.model_validate(
        {"ticker": "AAPL", "analysis_goal": "Identify risks.", "demo_mode": True}
    )
    ids = [asyncio_run(store.create(request)).run_id for _ in range(3)]
    recent = asyncio_run(store.list_recent(limit=2))
    assert [r.run_id for r in recent] == list(reversed(ids[-2:]))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def asyncio_run(coro):
    """Drive an awaitable to completion synchronously.

    Kept as a tiny helper so the test file does not need
    ``pytest-asyncio`` decoration on every case.
    """
    import asyncio

    return asyncio.run(coro)
