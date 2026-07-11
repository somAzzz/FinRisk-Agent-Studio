"""Independent lineage and formula checks for normalized financial snapshots."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from src.data.xbrl import extract_metric
from src.research.models import FinancialMetricPoint, FinancialSnapshot

ReconciliationStatus = Literal["passed", "failed", "not_applicable"]


@dataclass(frozen=True)
class MetricReconciliation:
    metric: str
    status: ReconciliationStatus
    expected_periods: int
    observed_periods: int
    checked_points: int
    errors: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class FinancialReconciliationReport:
    ticker: str
    metrics: tuple[MetricReconciliation, ...]

    @property
    def passed(self) -> bool:
        return all(item.status != "failed" for item in self.metrics)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)


def _reported_matches_raw(point: FinancialMetricPoint, facts: dict) -> bool:
    rows = extract_metric(facts, concept=point.source_concept, unit=point.unit)
    return any(
        row.period_end == point.period_end
        and row.accession_number == point.accession_number
        and row.filed_at == point.filed_at
        and _close(row.value, point.value)
        for row in rows
    )


def _find_point(
    points: Iterable[FinancialMetricPoint],
    *,
    period_kind: str,
    period_end: object | None = None,
    period_start: object | None = None,
) -> FinancialMetricPoint | None:
    return next(
        (
            item
            for item in points
            if item.period_kind == period_kind
            and (period_end is None or item.period_end == period_end)
            and (period_start is None or item.period_start == period_start)
        ),
        None,
    )


def _derived_quarter_matches(
    point: FinancialMetricPoint,
    metric_points: list[FinancialMetricPoint],
) -> bool:
    if point.derivation == "FY - Q3 YTD":
        current = _find_point(
            metric_points,
            period_kind="annual",
            period_end=point.period_end,
        )
        prior = max(
            (
                item
                for item in metric_points
                if item.period_kind == "year_to_date"
                and current is not None
                and item.period_start == current.period_start
                and item.period_end < current.period_end
            ),
            key=lambda item: item.period_end,
            default=None,
        )
    elif point.derivation == "Q2 YTD - Q1 cumulative":
        current = _find_point(
            metric_points,
            period_kind="year_to_date",
            period_end=point.period_end,
        )
        prior = _find_point(
            metric_points,
            period_kind="quarter",
            period_start=current.period_start if current else None,
        )
    elif point.derivation == "Q3 YTD - Q2 cumulative":
        current = _find_point(
            metric_points,
            period_kind="year_to_date",
            period_end=point.period_end,
        )
        prior = max(
            (
                item
                for item in metric_points
                if item.period_kind == "year_to_date"
                and current is not None
                and item.period_start == current.period_start
                and item.period_end < current.period_end
            ),
            key=lambda item: item.period_end,
            default=None,
        )
    else:
        return False
    return bool(current and prior and _close(point.value, current.value - prior.value))


def _derived_point_matches(
    point: FinancialMetricPoint,
    snapshot: FinancialSnapshot,
) -> bool:
    if point.derivation == "operating_cash_flow - abs(capital_expenditure)":
        operating_cash_flow = next(
            (
                item
                for item in snapshot.metrics
                if item.metric == "operating_cash_flow"
                and item.period_end == point.period_end
                and item.period_kind == point.period_kind
            ),
            None,
        )
        capex = next(
            (
                item
                for item in snapshot.metrics
                if item.metric == "capital_expenditure"
                and item.period_end == point.period_end
                and item.period_kind == point.period_kind
            ),
            None,
        )
        return bool(
            operating_cash_flow
            and capex
            and _close(point.value, operating_cash_flow.value - abs(capex.value))
        )
    metric_points = [
        item for item in snapshot.metrics if item.metric == point.metric
    ]
    return _derived_quarter_matches(point, metric_points)


def _ttm_matches(point: FinancialMetricPoint, snapshot: FinancialSnapshot) -> bool:
    quarters = [
        item
        for item in snapshot.series(point.metric, "quarter")
        if item.period_end <= point.period_end
    ][-4:]
    return (
        len(quarters) == 4
        and quarters[-1].period_end == point.period_end
        and _close(point.value, sum(item.value for item in quarters))
    )


def reconcile_financial_snapshot(
    snapshot: FinancialSnapshot,
    facts: dict,
    *,
    metrics: Iterable[str],
    expected_periods: int = 12,
    allowed_missing: Iterable[str] = (),
) -> FinancialReconciliationReport:
    """Check coverage, raw SEC lineage, quarter derivations, and TTM sums."""
    allowed = set(allowed_missing)
    results: list[MetricReconciliation] = []
    for metric in metrics:
        quarter_points = snapshot.series(metric, "quarter")[-expected_periods:]
        selected = quarter_points
        if not selected:
            selected = snapshot.series(metric, "instant")[-expected_periods:]
        if not selected:
            selected = snapshot.series(metric, "annual")[-expected_periods:]
        if not selected and metric in allowed:
            results.append(
                MetricReconciliation(
                    metric=metric,
                    status="not_applicable",
                    expected_periods=expected_periods,
                    observed_periods=0,
                    checked_points=0,
                    note="issuer does not report a stable standard concept",
                )
            )
            continue

        errors: list[str] = []
        if len(selected) < expected_periods:
            errors.append(f"coverage:{len(selected)}/{expected_periods}")
        for point in selected:
            matches = (
                _reported_matches_raw(point, facts)
                if point.status == "reported"
                else _derived_point_matches(point, snapshot)
            )
            if not matches:
                errors.append(f"lineage_or_formula:{point.period_end}")

        ttm_points = [
            point
            for point in snapshot.series(metric, "ttm")
            if selected and point.period_end >= selected[0].period_end
        ]
        for point in ttm_points:
            if not _ttm_matches(point, snapshot):
                errors.append(f"ttm_formula:{point.period_end}")
        results.append(
            MetricReconciliation(
                metric=metric,
                status="failed" if errors else "passed",
                expected_periods=expected_periods,
                observed_periods=len(selected),
                checked_points=len(selected) + len(ttm_points),
                errors=tuple(errors),
            )
        )
    return FinancialReconciliationReport(
        ticker=snapshot.ticker,
        metrics=tuple(results),
    )
