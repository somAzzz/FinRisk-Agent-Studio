"""Comparable company facts and evidence-based research queue generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.research.change_detection import ResearchChangeSet
from src.research.expectations import ExpectationPoint
from src.research.models import CompanyResearchSnapshot, FinancialMetricPoint, PeriodKind
from src.research.valuation import (
    MultipleValuationRequest,
    MultipleValuationResponse,
    calculate_multiple_valuation,
)


class CompanyComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_ids: list[str] = Field(min_length=2, max_length=20)
    metrics: list[str] = Field(min_length=1, max_length=30)
    period_kind: PeriodKind = "ttm"

    @field_validator("snapshot_ids")
    @classmethod
    def _unique_snapshots(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("snapshot_ids must be unique")
        return value


class ComparableMetricValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    metric: str
    value: float | None = None
    unit: str | None = None
    period_end: str | None = None
    source_as_of: str | None = None
    freshness_days: int | None = None
    status: Literal["reported", "derived", "not_available", "not_comparable"]
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class CompanyComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    period_kind: PeriodKind
    tickers: list[str]
    values: list[ComparableMetricValue]
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str


class PeerAnalysisRequest(CompanyComparisonRequest):
    valuations: list[MultipleValuationRequest] = Field(default_factory=list, max_length=90)


class PeerRiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    total: int
    new: int
    strengthened: int
    weakened: int
    evidence_ids: list[str]


class PeerExpectationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    metric: str
    fiscal_period: str
    value: float
    unit: str
    source: str
    as_of: str


class PeerAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    financials: CompanyComparisonResponse
    risks: list[PeerRiskSummary]
    expectations: list[PeerExpectationSummary]
    valuations: list[MultipleValuationResponse]
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str


class ResearchQueueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    priority: Literal["high", "medium", "low"]
    reasons: list[str]
    change_ids: list[str]
    evidence_ids: list[str]


class ResearchQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[ResearchQueueEntry]
    disclaimer: str


def compare_company_snapshots(
    snapshots: list[CompanyResearchSnapshot],
    *,
    metrics: list[str],
    period_kind: PeriodKind,
    strict_as_of: bool = True,
) -> CompanyComparisonResponse:
    if len(snapshots) < 2:
        raise ValueError("at least two snapshots are required")
    dates = {snapshot.as_of.date() for snapshot in snapshots}
    if strict_as_of and len(dates) != 1:
        raise ValueError("all snapshots must use the same as_of date")
    comparison_date = max(dates)
    tickers = [snapshot.ticker for snapshot in snapshots]
    if len(tickers) != len(set(tickers)):
        raise ValueError("snapshots must represent different companies")
    currencies = {snapshot.financials.currency for snapshot in snapshots if snapshot.financials is not None}
    common_currency = next(iter(currencies)) if len(currencies) == 1 else None
    warnings = []
    if len(currencies) > 1:
        warnings.append("Currency mismatch: monetary values are marked not comparable.")
    if len(dates) > 1:
        warnings.append(
            "Snapshot dates differ; freshness_days is shown for each company."
        )
    values: list[ComparableMetricValue] = []
    for metric in metrics:
        for snapshot in snapshots:
            financials = snapshot.financials
            if financials is None:
                values.append(
                    ComparableMetricValue(
                        ticker=snapshot.ticker,
                        metric=metric,
                        status="not_available",
                        source_as_of=snapshot.as_of.date().isoformat(),
                        freshness_days=(comparison_date - snapshot.as_of.date()).days,
                        reason="financial snapshot unavailable",
                    )
                )
                continue
            point = _latest_point(financials.metrics, metric, period_kind)
            if point is None:
                values.append(
                    ComparableMetricValue(
                        ticker=snapshot.ticker,
                        metric=metric,
                        status="not_available",
                        source_as_of=snapshot.as_of.date().isoformat(),
                        freshness_days=(comparison_date - snapshot.as_of.date()).days,
                        reason=f"no {period_kind} value",
                    )
                )
                continue
            monetary = point.unit.upper() in {"USD", "EUR", "GBP", "JPY", "CNY"}
            if monetary and common_currency is None:
                values.append(
                    ComparableMetricValue(
                        ticker=snapshot.ticker,
                        metric=metric,
                        unit=point.unit,
                        period_end=point.period_end.isoformat(),
                        status="not_comparable",
                        evidence_ids=_evidence(point),
                        source_as_of=snapshot.as_of.date().isoformat(),
                        freshness_days=(comparison_date - snapshot.as_of.date()).days,
                        reason="currency mismatch",
                    )
                )
                continue
            values.append(
                ComparableMetricValue(
                    ticker=snapshot.ticker,
                    metric=metric,
                    value=point.value,
                    unit=point.unit,
                    period_end=point.period_end.isoformat(),
                    status=point.status,
                    evidence_ids=_evidence(point),
                    source_as_of=snapshot.as_of.date().isoformat(),
                    freshness_days=(comparison_date - snapshot.as_of.date()).days,
                )
            )
    return CompanyComparisonResponse(
        as_of=comparison_date.isoformat(),
        period_kind=period_kind,
        tickers=tickers,
        values=values,
        warnings=warnings,
        disclaimer=(
            "This table normalizes point-in-time research facts. It is not a ranking, "
            "recommendation, or substitute for company-specific analysis."
        ),
    )


def build_research_queue(
    change_sets: list[ResearchChangeSet],
) -> ResearchQueueResponse:
    entries: list[ResearchQueueEntry] = []
    for change_set in change_sets:
        actionable = [
            change
            for change in change_set.changes
            if change.materiality in {"high", "medium", "unknown"} and change.analyst_review_status != "ignored"
        ]
        if not actionable:
            continue
        high_count = sum(change.materiality == "high" for change in actionable)
        unknown_count = sum(change.materiality == "unknown" for change in actionable)
        priority: Literal["high", "medium", "low"]
        if high_count:
            priority = "high"
        elif unknown_count or len(actionable) >= 2:
            priority = "medium"
        else:
            priority = "low"
        reasons = [f"{change.materiality} {change.category} change: {change.key}" for change in actionable]
        entries.append(
            ResearchQueueEntry(
                ticker=change_set.ticker,
                priority=priority,
                reasons=reasons,
                change_ids=[change.change_id for change in actionable],
                evidence_ids=sorted({evidence for change in actionable for evidence in change.after_evidence_ids}),
            )
        )
    rank = {"high": 0, "medium": 1, "low": 2}
    return ResearchQueueResponse(
        entries=sorted(entries, key=lambda item: (rank[item.priority], item.ticker)),
        disclaimer=(
            "The queue orders evidence review work only. It is not an investment "
            "score, recommendation, or trading signal."
        ),
    )


def build_peer_analysis(
    snapshots: list[CompanyResearchSnapshot],
    *,
    request: PeerAnalysisRequest,
    expectations_by_ticker: dict[str, list[ExpectationPoint]],
) -> PeerAnalysisResponse:
    financials = compare_company_snapshots(
        snapshots,
        metrics=request.metrics,
        period_kind=request.period_kind,
        strict_as_of=False,
    )
    risks = [
        PeerRiskSummary(
            ticker=snapshot.ticker,
            total=len(snapshot.risks),
            new=sum(item.status == "new" for item in snapshot.risks),
            strengthened=sum(item.status == "strengthened" for item in snapshot.risks),
            weakened=sum(item.status == "weakened" for item in snapshot.risks),
            evidence_ids=sorted(
                {
                    evidence_id
                    for risk in snapshot.risks
                    for evidence_id in risk.evidence_ids
                }
            ),
        )
        for snapshot in snapshots
    ]
    expectations: list[PeerExpectationSummary] = []
    for ticker, points in expectations_by_ticker.items():
        latest: dict[tuple[str, str], ExpectationPoint] = {}
        for point in points:
            key = (point.metric, point.fiscal_period)
            current = latest.get(key)
            if current is None or point.as_of > current.as_of:
                latest[key] = point
        expectations.extend(
            PeerExpectationSummary(
                ticker=ticker,
                metric=point.metric,
                fiscal_period=point.fiscal_period,
                value=point.value,
                unit=point.unit,
                source=point.source,
                as_of=point.as_of.isoformat(),
            )
            for point in latest.values()
        )
    member_tickers = {snapshot.ticker for snapshot in snapshots}
    invalid_valuations = sorted(
        {
            item.ticker.upper().strip()
            for item in request.valuations
            if item.ticker.upper().strip() not in member_tickers
        }
    )
    if invalid_valuations:
        raise ValueError(
            f"valuation tickers are not in the peer snapshots: {invalid_valuations}"
        )
    valuations = [calculate_multiple_valuation(item) for item in request.valuations]
    warnings = list(financials.warnings)
    missing_valuation = sorted(member_tickers - {item.ticker for item in valuations})
    if missing_valuation:
        warnings.append(
            "Valuation inputs were not supplied for: " + ", ".join(missing_valuation)
        )
    return PeerAnalysisResponse(
        financials=financials,
        risks=risks,
        expectations=sorted(
            expectations,
            key=lambda item: (item.ticker, item.metric, item.fiscal_period),
        ),
        valuations=valuations,
        warnings=warnings,
        disclaimer=(
            "Peer analysis keeps financial, risk, expectation and valuation "
            "lineage separate; it is not a composite score or recommendation."
        ),
    )


def _latest_point(
    points: list[FinancialMetricPoint],
    metric: str,
    period_kind: PeriodKind,
) -> FinancialMetricPoint | None:
    candidates = [point for point in points if point.metric == metric and point.period_kind == period_kind]
    return max(candidates, key=lambda point: point.period_end) if candidates else None


def _evidence(point: FinancialMetricPoint) -> list[str]:
    return sorted(set(point.source_accession_numbers or ([point.accession_number] if point.accession_number else [])))


__all__ = [
    "CompanyComparisonRequest",
    "CompanyComparisonResponse",
    "PeerAnalysisRequest",
    "PeerAnalysisResponse",
    "ResearchQueueEntry",
    "ResearchQueueResponse",
    "build_peer_analysis",
    "build_research_queue",
    "compare_company_snapshots",
]
