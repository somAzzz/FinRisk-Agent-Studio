from __future__ import annotations

from src.research.change_detection import (
    ChangeReviewRequest,
    ResearchChange,
    ResearchChangeSet,
)
from src.research.change_store import ResearchChangeStore


def test_change_review_is_persisted_and_reapplied(tmp_path) -> None:
    store = ResearchChangeStore(tmp_path / "changes.sqlite")
    change = ResearchChange(
        change_id="change-one",
        ticker="ACME",
        category="risk",
        key="supply",
        status="new",
        materiality="medium",
        detection_method="test",
        explanation="New risk",
        confidence=1.0,
    )
    change_set = ResearchChangeSet(
        ticker="ACME",
        from_snapshot_id="old",
        to_snapshot_id="new",
        changes=[change],
    )
    store.save_change_set(change_set)

    reviewed = store.review_change(
        change.change_id,
        ChangeReviewRequest(status="confirmed", notes="Checked filing"),
    )
    refreshed = store.save_change_set(change_set)

    assert reviewed.analyst_review_status == "confirmed"
    assert refreshed.changes[0].analyst_review_status == "confirmed"
