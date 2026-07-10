"""Point-in-time analyst expectations with CSV import and surprise analysis."""

from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.research.models import FinancialMetricPoint

ExpectationOrigin = Literal["user", "csv", "provider"]


class ExpectationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_id: str | None = None
    ticker: str
    metric: str
    fiscal_period: str
    value: float
    unit: str
    source: str
    origin: ExpectationOrigin = "user"
    observed_at: datetime
    as_of: datetime
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned

    @field_validator("metric", "fiscal_period", "unit", "source")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("observed_at", "as_of")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expectation timestamps must include a timezone")
        return value.astimezone(UTC)

    def model_post_init(self, _context: object) -> None:
        if self.as_of < self.observed_at:
            raise ValueError("as_of must not precede observed_at")
        if self.expectation_id is None:
            identity = "|".join(
                [
                    self.ticker,
                    self.metric,
                    self.fiscal_period,
                    self.source,
                    self.observed_at.isoformat(),
                ]
            )
            self.expectation_id = f"expectation-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


class ExpectationImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imported: int
    skipped: int
    expectation_ids: list[str] = Field(default_factory=list)


class ExpectationComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation: ExpectationPoint
    actual: FinancialMetricPoint
    absolute_surprise: float
    percent_surprise: float | None = None


class ExpectationStore:
    REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "ticker",
        "metric",
        "fiscal_period",
        "value",
        "unit",
        "source",
        "observed_at",
        "as_of",
    }

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
                CREATE TABLE IF NOT EXISTS research_expectations (
                    expectation_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    fiscal_period TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(ticker, metric, fiscal_period, source, observed_at)
                )
                """
            )

    def save(self, point: ExpectationPoint) -> tuple[ExpectationPoint, bool]:
        if point.expectation_id is None:
            raise ValueError("expectation_id was not generated")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM research_expectations WHERE expectation_id = ?",
                (point.expectation_id,),
            ).fetchone()
            if existing:
                return ExpectationPoint.model_validate_json(existing["payload"]), False
            connection.execute(
                """
                INSERT INTO research_expectations
                    (expectation_id, ticker, metric, fiscal_period, source,
                     observed_at, as_of, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    point.expectation_id,
                    point.ticker,
                    point.metric,
                    point.fiscal_period,
                    point.source,
                    point.observed_at.isoformat(),
                    point.as_of.isoformat(),
                    point.model_dump_json(),
                ),
            )
        return point, True

    def list(
        self,
        *,
        ticker: str,
        metric: str | None = None,
        fiscal_period: str | None = None,
        known_on_or_before: datetime | None = None,
    ) -> list[ExpectationPoint]:
        clauses = ["ticker = ?"]
        parameters: list[str] = [ticker.upper().strip()]
        if metric:
            clauses.append("metric = ?")
            parameters.append(metric)
        if fiscal_period:
            clauses.append("fiscal_period = ?")
            parameters.append(fiscal_period)
        if known_on_or_before:
            clauses.append("as_of <= ?")
            parameters.append(known_on_or_before.isoformat())
        query = "SELECT payload FROM research_expectations WHERE " + " AND ".join(clauses) + " ORDER BY as_of DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ExpectationPoint.model_validate_json(row["payload"]) for row in rows]

    def get(self, expectation_id: str) -> ExpectationPoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_expectations WHERE expectation_id = ?",
                (expectation_id,),
            ).fetchone()
        return ExpectationPoint.model_validate_json(row["payload"]) if row else None

    def import_csv(self, content: str) -> ExpectationImportResult:
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None:
            raise ValueError("CSV header is required")
        missing = self.REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        imported = 0
        skipped = 0
        ids: list[str] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                point = ExpectationPoint(
                    ticker=row["ticker"],
                    metric=row["metric"],
                    fiscal_period=row["fiscal_period"],
                    value=float(row["value"]),
                    unit=row["unit"],
                    source=row["source"],
                    origin="csv",
                    observed_at=_parse_datetime(row["observed_at"]),
                    as_of=_parse_datetime(row["as_of"]),
                    notes=row.get("notes") or None,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid CSV row {row_number}: {exc}") from exc
            saved, created = self.save(point)
            if saved.expectation_id:
                ids.append(saved.expectation_id)
            imported += int(created)
            skipped += int(not created)
        return ExpectationImportResult(
            imported=imported,
            skipped=skipped,
            expectation_ids=ids,
        )


def compare_expectation_to_actual(
    expectation: ExpectationPoint,
    actual: FinancialMetricPoint,
) -> ExpectationComparison:
    if expectation.metric != actual.metric:
        raise ValueError("expectation and actual metric must match")
    if expectation.unit != actual.unit:
        raise ValueError("expectation and actual unit must match")
    if actual.filed_at is not None:
        filed_at = datetime(
            actual.filed_at.year,
            actual.filed_at.month,
            actual.filed_at.day,
            tzinfo=UTC,
        )
        if expectation.as_of >= filed_at:
            raise ValueError("expectation must be known before the actual was filed")
    absolute = actual.value - expectation.value
    percent = absolute / abs(expectation.value) if expectation.value else None
    return ExpectationComparison(
        expectation=expectation,
        actual=actual,
        absolute_surprise=absolute,
        percent_surprise=percent,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


__all__ = [
    "ExpectationComparison",
    "ExpectationImportResult",
    "ExpectationPoint",
    "ExpectationStore",
    "compare_expectation_to_actual",
]
