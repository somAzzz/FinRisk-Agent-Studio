"""Persistence for detected research changes and analyst review state."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.research.change_detection import (
    ChangeReviewRequest,
    ResearchChange,
    ResearchChangeSet,
)


class ResearchChangeStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_changes (
                    change_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    from_snapshot_id TEXT NOT NULL,
                    to_snapshot_id TEXT NOT NULL,
                    materiality TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_change_reviews (
                    change_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    notes TEXT,
                    reviewed_at TEXT NOT NULL
                )
                """
            )

    def save_change_set(self, change_set: ResearchChangeSet) -> ResearchChangeSet:
        with self._connect() as connection:
            for change in change_set.changes:
                connection.execute(
                    """
                    INSERT INTO research_changes
                        (change_id, ticker, from_snapshot_id, to_snapshot_id,
                         materiality, created_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(change_id) DO NOTHING
                    """,
                    (
                        change.change_id,
                        change.ticker,
                        change_set.from_snapshot_id,
                        change_set.to_snapshot_id,
                        change.materiality,
                        change_set.generated_at.isoformat(),
                        change.model_dump_json(),
                    ),
                )
        return self.apply_reviews(change_set)

    def apply_reviews(self, change_set: ResearchChangeSet) -> ResearchChangeSet:
        with self._connect() as connection:
            rows = connection.execute("SELECT change_id, status FROM research_change_reviews").fetchall()
        reviews = {row["change_id"]: row["status"] for row in rows}
        return change_set.model_copy(
            update={
                "changes": [
                    change.model_copy(update={"analyst_review_status": reviews[change.change_id]})
                    if change.change_id in reviews
                    else change
                    for change in change_set.changes
                ]
            }
        )

    def review_change(self, change_id: str, review: ChangeReviewRequest) -> ResearchChange:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_changes WHERE change_id = ?",
                (change_id,),
            ).fetchone()
            if row is None:
                raise KeyError(change_id)
            connection.execute(
                """
                INSERT INTO research_change_reviews
                    (change_id, status, notes, reviewed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(change_id) DO UPDATE SET
                    status=excluded.status,
                    notes=excluded.notes,
                    reviewed_at=excluded.reviewed_at
                """,
                (change_id, review.status, review.notes, datetime.now(UTC).isoformat()),
            )
        change = ResearchChange.model_validate_json(row["payload"])
        return change.model_copy(update={"analyst_review_status": review.status})


__all__ = ["ResearchChangeStore"]
