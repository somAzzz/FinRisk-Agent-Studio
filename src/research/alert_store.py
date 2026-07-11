"""Persistent, deduplicated in-app alerts for research changes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.change_detection import Materiality, ResearchChange
from src.research.database import apply_migrations

AlertStatus = Literal["new", "acknowledged", "ignored"]


class ResearchAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    change_id: str
    ticker: str
    materiality: Materiality
    title: str
    explanation: str
    status: AlertStatus = "new"
    snapshot_id: str
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlertActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["acknowledge", "ignore"]


class MonitorCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    snapshot_id: str
    source_fingerprint: str
    last_success_at: datetime
    source_cursors: dict[str, str] = Field(default_factory=dict)


class ResearchAlertStore:
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
                CREATE TABLE IF NOT EXISTS research_alerts (
                    alert_id TEXT PRIMARY KEY,
                    change_id TEXT NOT NULL UNIQUE,
                    ticker TEXT NOT NULL,
                    materiality TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_monitor_cursors (
                    ticker TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    last_success_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def create_for_change(
        self,
        change: ResearchChange,
        *,
        snapshot_id: str,
        correlation_id: str | None = None,
    ) -> tuple[ResearchAlert, bool]:
        alert = ResearchAlert(
            alert_id=f"alert-{change.change_id.removeprefix('change-')}",
            change_id=change.change_id,
            ticker=change.ticker,
            materiality=change.materiality,
            title=f"{change.category}: {change.key}",
            explanation=change.explanation,
            snapshot_id=snapshot_id,
            correlation_id=correlation_id,
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_alerts WHERE change_id = ?",
                (change.change_id,),
            ).fetchone()
            if row:
                return ResearchAlert.model_validate_json(row["payload"]), False
            connection.execute(
                """
                INSERT INTO research_alerts
                    (alert_id, change_id, ticker, materiality, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.change_id,
                    alert.ticker,
                    alert.materiality,
                    alert.status,
                    alert.created_at.isoformat(),
                    alert.model_dump_json(),
                ),
            )
        return alert, True

    def list_alerts(
        self,
        *,
        ticker: str | None = None,
        status: AlertStatus | None = None,
    ) -> list[ResearchAlert]:
        clauses: list[str] = []
        parameters: list[str] = []
        if ticker:
            clauses.append("ticker = ?")
            parameters.append(ticker.upper().strip())
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM research_alerts{where} ORDER BY created_at DESC",
                parameters,
            ).fetchall()
        return [ResearchAlert.model_validate_json(row["payload"]) for row in rows]

    def act(self, alert_id: str, action: AlertActionRequest) -> ResearchAlert:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
            if row is None:
                raise KeyError(alert_id)
            alert = ResearchAlert.model_validate_json(row["payload"])
            updated = alert.model_copy(
                update={
                    "status": ("acknowledged" if action.action == "acknowledge" else "ignored"),
                    "updated_at": datetime.now(UTC),
                }
            )
            connection.execute(
                "UPDATE research_alerts SET status = ?, payload = ? WHERE alert_id = ?",
                (updated.status, updated.model_dump_json(), alert_id),
            )
        return updated

    def save_cursor(self, cursor: MonitorCursor) -> MonitorCursor:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_monitor_cursors
                    (ticker, snapshot_id, source_fingerprint, last_success_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    snapshot_id=excluded.snapshot_id,
                    source_fingerprint=excluded.source_fingerprint,
                    last_success_at=excluded.last_success_at,
                    payload=excluded.payload
                """,
                (
                    cursor.ticker,
                    cursor.snapshot_id,
                    cursor.source_fingerprint,
                    cursor.last_success_at.isoformat(),
                    cursor.model_dump_json(),
                ),
            )
        return cursor

    def get_cursor(self, ticker: str) -> MonitorCursor | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_monitor_cursors WHERE ticker = ?",
                (ticker.upper().strip(),),
            ).fetchone()
        return MonitorCursor.model_validate_json(row["payload"]) if row else None


__all__ = [
    "AlertActionRequest",
    "MonitorCursor",
    "ResearchAlert",
    "ResearchAlertStore",
]
