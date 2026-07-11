"""SQLite persistence for immutable company research snapshots and runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.research.database import apply_migrations
from src.research.models import CompanyResearchSnapshot, ResearchRunManifest


class ResearchSnapshotStore:
    """Persist typed snapshots without mutating historical payloads."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    period TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(ticker, period, as_of, source_fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_research_snapshots_ticker_as_of
                ON research_snapshots(ticker, as_of DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    snapshot_id TEXT,
                    started_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save_snapshot(self, snapshot: CompanyResearchSnapshot) -> CompanyResearchSnapshot:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload FROM research_snapshots
                WHERE ticker = ? AND period = ? AND as_of = ? AND source_fingerprint = ?
                """,
                (
                    snapshot.ticker,
                    snapshot.period,
                    snapshot.as_of.isoformat(),
                    snapshot.source_fingerprint,
                ),
            ).fetchone()
            if existing:
                return CompanyResearchSnapshot.model_validate_json(existing["payload"])
            connection.execute(
                """
                INSERT INTO research_snapshots
                    (snapshot_id, ticker, period, as_of, source_fingerprint, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.ticker,
                    snapshot.period,
                    snapshot.as_of.isoformat(),
                    snapshot.source_fingerprint,
                    snapshot.created_at.isoformat(),
                    snapshot.model_dump_json(),
                ),
            )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> CompanyResearchSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return CompanyResearchSnapshot.model_validate_json(row["payload"]) if row else None

    def list_snapshots(self, ticker: str, *, limit: int = 20) -> list[CompanyResearchSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM research_snapshots
                WHERE ticker = ? ORDER BY as_of DESC LIMIT ?
                """,
                (ticker.upper().strip(), limit),
            ).fetchall()
        return [CompanyResearchSnapshot.model_validate_json(row["payload"]) for row in rows]

    def save_run(self, run: ResearchRunManifest) -> ResearchRunManifest:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_runs
                    (run_id, ticker, snapshot_id, started_at, state, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    snapshot_id=excluded.snapshot_id,
                    state=excluded.state,
                    payload=excluded.payload
                """,
                (
                    run.run_id,
                    run.ticker,
                    run.snapshot_id,
                    run.started_at.isoformat(),
                    run.state,
                    run.model_dump_json(),
                ),
            )
        return run

    def get_run(self, run_id: str) -> ResearchRunManifest | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return ResearchRunManifest.model_validate_json(row["payload"]) if row else None


__all__ = ["ResearchSnapshotStore"]
