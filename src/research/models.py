"""Typed models for point-in-time company research data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.management_snapshot import ManagementPeriodSnapshot

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
SnapshotComponentState = Literal[
    "complete",
    "partial",
    "not_requested",
    "unavailable",
    "failed",
]
ResearchRunState = Literal["completed", "partial", "failed"]


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
                if point.metric == metric and (period_kind is None or point.period_kind == period_kind)
            ),
            key=lambda point: (point.period_end, point.filed_at or date.min),
        )


class SourceManifestEntry(BaseModel):
    """One source included in a point-in-time research snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal["sec_filing", "transcript", "risk_report", "other"]
    provider: str
    as_of: datetime
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SnapshotComponentResult(BaseModel):
    """Availability and degradation state for one snapshot component."""

    model_config = ConfigDict(extra="forbid")

    component: Literal["financials", "management", "risks"]
    state: SnapshotComponentState
    reason: str | None = None
    source_count: int = 0


class RiskObservation(BaseModel):
    """Minimal evidence-linked risk carried into a company snapshot."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    title: str
    status: Literal["new", "persistent", "strengthened", "weakened", "resolved", "unknown"] = "unknown"
    severity: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class CompanyResearchSnapshot(BaseModel):
    """Immutable point-in-time company research state."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    correlation_id: str | None = None
    ticker: str
    period: str
    as_of: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_fingerprint: str
    financials: FinancialSnapshot | None = None
    management: ManagementPeriodSnapshot | None = None
    risks: list[RiskObservation] = Field(default_factory=list)
    components: list[SnapshotComponentResult] = Field(default_factory=list)
    sources: list[SourceManifestEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchRunManifest(BaseModel):
    """Auditable outcome of one snapshot orchestration request."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    correlation_id: str | None = None
    ticker: str
    requested_as_of: datetime
    started_at: datetime
    completed_at: datetime
    state: ResearchRunState
    snapshot_id: str | None = None
    components: list[SnapshotComponentResult] = Field(default_factory=list)
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
