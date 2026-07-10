from __future__ import annotations

from datetime import UTC, datetime

from src.research.models import CompanyResearchSnapshot, SnapshotComponentResult
from src.research.snapshot_store import ResearchSnapshotStore


def _snapshot(snapshot_id: str = "snapshot-one") -> CompanyResearchSnapshot:
    return CompanyResearchSnapshot(
        snapshot_id=snapshot_id,
        ticker="ACME",
        period="2026Q1",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        source_fingerprint="fingerprint-one",
        components=[SnapshotComponentResult(component="financials", state="complete")],
    )


def test_snapshot_store_preserves_immutable_idempotent_snapshot(tmp_path) -> None:
    store = ResearchSnapshotStore(tmp_path / "snapshots.sqlite")

    first = store.save_snapshot(_snapshot())
    duplicate = store.save_snapshot(_snapshot("snapshot-different"))

    assert duplicate.snapshot_id == first.snapshot_id
    assert store.get_snapshot(first.snapshot_id) == first
    assert store.list_snapshots("acme") == [first]


def test_snapshot_store_returns_none_for_unknown_records(tmp_path) -> None:
    store = ResearchSnapshotStore(tmp_path / "snapshots.sqlite")

    assert store.get_snapshot("missing") is None
    assert store.get_run("missing") is None
