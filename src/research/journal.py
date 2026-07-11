"""Persistent personal research journal for theses and watchlists."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.research.database import apply_migrations

ThesisStatus = Literal["draft", "active", "invalidated", "closed"]
ReviewOutcome = Literal["supported", "mixed", "invalidated", "unknown"]
CatalystStatus = Literal["upcoming", "occurred", "missed", "cancelled"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Catalyst(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalyst_id: str = Field(default_factory=lambda: f"cat-{uuid.uuid4().hex[:12]}")
    title: str
    expected_date: date | None = None
    status: CatalystStatus = "upcoming"
    evidence_ids: list[str] = Field(default_factory=list)


class ThesisReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: f"review-{uuid.uuid4().hex[:12]}")
    reviewed_at: datetime = Field(default_factory=_utcnow)
    outcome: ReviewOutcome
    notes: str
    evidence_ids: list[str] = Field(default_factory=list)


class InvestmentThesis(BaseModel):
    """A research hypothesis with explicit falsification conditions."""

    model_config = ConfigDict(extra="forbid")

    thesis_id: str = Field(default_factory=lambda: f"thesis-{uuid.uuid4().hex[:12]}")
    ticker: str
    statement: str
    time_horizon: str
    status: ThesisStatus = "draft"
    key_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    disconfirming_conditions: list[str] = Field(min_length=1)
    monitoring_metrics: list[str] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reviews: list[ThesisReview] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned


class WatchlistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    thesis_ids: list[str] = Field(default_factory=list)
    monitoring_questions: list[str] = Field(default_factory=list)
    next_review_date: date | None = None
    active: bool = True
    research_components: list[Literal["management", "risks"]] = Field(
        default_factory=lambda: ["risks"]
    )
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned


class ResearchReminder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder_id: str
    ticker: str
    reminder_type: Literal["thesis_review", "catalyst"]
    title: str
    due_date: date
    overdue: bool
    thesis_id: str | None = None
    catalyst_id: str | None = None


class ResearchJournalStore:
    """SQLite-backed journal with one JSON payload per typed record."""

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
                CREATE TABLE IF NOT EXISTS research_theses (
                    thesis_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_watchlist (
                    ticker TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save_thesis(self, thesis: InvestmentThesis) -> InvestmentThesis:
        saved = thesis.model_copy(update={"updated_at": _utcnow()})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_theses
                    (thesis_id, ticker, status, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thesis_id) DO UPDATE SET
                    ticker=excluded.ticker,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    saved.thesis_id,
                    saved.ticker,
                    saved.status,
                    saved.updated_at.isoformat(),
                    saved.model_dump_json(),
                ),
            )
        return saved

    def get_thesis(self, thesis_id: str) -> InvestmentThesis | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_theses WHERE thesis_id = ?",
                (thesis_id,),
            ).fetchone()
        return InvestmentThesis.model_validate_json(row["payload"]) if row else None

    def list_theses(
        self,
        *,
        ticker: str | None = None,
        status: ThesisStatus | None = None,
    ) -> list[InvestmentThesis]:
        clauses: list[str] = []
        parameters: list[str] = []
        if ticker:
            clauses.append("ticker = ?")
            parameters.append(ticker.upper())
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT payload FROM research_theses{where} ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [InvestmentThesis.model_validate_json(row["payload"]) for row in rows]

    def add_review(self, thesis_id: str, review: ThesisReview) -> InvestmentThesis:
        thesis = self.get_thesis(thesis_id)
        if thesis is None:
            raise KeyError(thesis_id)
        status: ThesisStatus = thesis.status
        if review.outcome == "invalidated":
            status = "invalidated"
        return self.save_thesis(
            thesis.model_copy(
                update={"reviews": [*thesis.reviews, review], "status": status}
            )
        )

    def save_watchlist_item(self, item: WatchlistItem) -> WatchlistItem:
        saved = item.model_copy(update={"updated_at": _utcnow()})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_watchlist (ticker, updated_at, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (saved.ticker, saved.updated_at.isoformat(), saved.model_dump_json()),
            )
        return saved

    def list_watchlist(self, *, active_only: bool = True) -> list[WatchlistItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM research_watchlist ORDER BY updated_at DESC"
            ).fetchall()
        items = [WatchlistItem.model_validate_json(row["payload"]) for row in rows]
        return [item for item in items if item.active] if active_only else items

    def list_due_reminders(
        self,
        *,
        as_of: date,
        horizon_days: int = 14,
    ) -> list[ResearchReminder]:
        cutoff = as_of + timedelta(days=horizon_days)
        reminders: list[ResearchReminder] = []
        for item in self.list_watchlist():
            if item.next_review_date and item.next_review_date <= cutoff:
                reminders.append(
                    ResearchReminder(
                        reminder_id=(
                            f"review:{item.ticker}:{item.next_review_date.isoformat()}"
                        ),
                        ticker=item.ticker,
                        reminder_type="thesis_review",
                        title=f"Review {item.ticker} research thesis",
                        due_date=item.next_review_date,
                        overdue=item.next_review_date < as_of,
                    )
                )
        for thesis in self.list_theses(status="active"):
            for catalyst in thesis.catalysts:
                if (
                    catalyst.status == "upcoming"
                    and catalyst.expected_date
                    and catalyst.expected_date <= cutoff
                ):
                    reminders.append(
                        ResearchReminder(
                            reminder_id=f"catalyst:{catalyst.catalyst_id}",
                            ticker=thesis.ticker,
                            reminder_type="catalyst",
                            title=catalyst.title,
                            due_date=catalyst.expected_date,
                            overdue=catalyst.expected_date < as_of,
                            thesis_id=thesis.thesis_id,
                            catalyst_id=catalyst.catalyst_id,
                        )
                    )
        return sorted(reminders, key=lambda item: (item.due_date, item.ticker))


__all__ = [
    "Catalyst",
    "InvestmentThesis",
    "ResearchJournalStore",
    "ResearchReminder",
    "ThesisReview",
    "WatchlistItem",
]
