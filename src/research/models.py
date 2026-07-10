"""Typed models for point-in-time company research data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PeriodKind = Literal[
    "quarter",
    "year_to_date",
    "annual",
    "ttm",
    "instant",
    "unknown",
]
MetricStatus = Literal["reported", "derived"]
ChangeType = Literal["qoq", "yoy", "annual_yoy", "ttm_yoy"]


class FinancialMetricPoint(BaseModel):
    """One normalized metric with its original SEC lineage."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    unit: str
    period_end: date
    period_start: date | None = None
    period_kind: PeriodKind = "unknown"
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form_type: str | None = None
    accession_number: str | None = None
    filed_at: date | None = None
    source_concept: str
    status: MetricStatus = "reported"
    derivation: str | None = None
    source_accession_numbers: list[str] = Field(default_factory=list)


class FinancialChange(BaseModel):
    """Period-over-period movement calculated from comparable periods."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    change_type: ChangeType
    current_period_end: date
    comparison_period_end: date
    current_value: float
    comparison_value: float
    absolute_change: float
    percent_change: float | None = None
    unit: str
    source_accession_numbers: list[str] = Field(default_factory=list)


class FinancialSnapshot(BaseModel):
    """Normalized SEC financial history for one company as of a point in time."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    cik: str
    company_name: str | None = None
    as_of: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    currency: str = "USD"
    metrics: list[FinancialMetricPoint] = Field(default_factory=list)
    changes: list[FinancialChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def series(
        self,
        metric: str,
        period_kind: PeriodKind | None = None,
    ) -> list[FinancialMetricPoint]:
        """Return one metric ordered from oldest to newest period."""
        return sorted(
            (
                point
                for point in self.metrics
                if point.metric == metric
                and (period_kind is None or point.period_kind == period_kind)
            ),
            key=lambda point: (point.period_end, point.filed_at or date.min),
        )
