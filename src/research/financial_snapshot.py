"""Build analyst-ready financial histories from SEC company facts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from itertools import pairwise
from typing import Literal

from src.data.xbrl import FactValue, extract_metric
from src.research.metric_config import MetricTemplate, load_metric_template
from src.research.models import (
    ChangeType,
    FinancialChange,
    FinancialMetricPoint,
    FinancialSnapshot,
    PeriodKind,
)

_GENERAL_TEMPLATE = load_metric_template()
INSTANT_METRICS = _GENERAL_TEMPLATE.instant_metrics | {"total_debt"}
SHARE_METRICS = {"diluted_shares"}
TTM_SUM_METRICS = _GENERAL_TEMPLATE.ttm_metrics | {"free_cash_flow"}
MARGIN_METRICS = {
    "gross_profit": "gross_margin",
    "operating_income": "operating_margin",
    "net_income": "net_margin",
}
RestatementPolicy = Literal["latest_known", "original", "amended_only"]


def _base_form(form_type: str | None) -> str | None:
    return form_type.removesuffix("/A") if form_type else None


def merge_company_facts(*payloads: dict) -> dict:
    """Merge SEC companyfacts across a current registrant and predecessors."""
    merged: dict = {"facts": {}}
    for payload in payloads:
        facts = payload.get("facts") if isinstance(payload, dict) else None
        if not isinstance(facts, dict):
            continue
        for taxonomy_name, taxonomy in facts.items():
            if not isinstance(taxonomy, dict):
                continue
            merged_taxonomy = merged["facts"].setdefault(taxonomy_name, {})
            for concept_name, concept in taxonomy.items():
                if not isinstance(concept, dict):
                    continue
                merged_concept = merged_taxonomy.setdefault(
                    concept_name,
                    {key: value for key, value in concept.items() if key != "units"},
                )
                merged_units = merged_concept.setdefault("units", {})
                units = concept.get("units")
                if not isinstance(units, dict):
                    continue
                for unit, rows in units.items():
                    if isinstance(rows, list):
                        merged_units.setdefault(unit, []).extend(rows)
    return merged


def _is_next_quarter(
    previous: FinancialMetricPoint,
    current: FinancialMetricPoint,
) -> bool:
    return 60 <= (current.period_end - previous.period_end).days <= 120


def _is_year_apart(
    previous: FinancialMetricPoint,
    current: FinancialMetricPoint,
) -> bool:
    return 330 <= (current.period_end - previous.period_end).days <= 400


def _period_kind(
    fact: FactValue,
    metric: str,
    instant_metrics: set[str] = INSTANT_METRICS,
) -> PeriodKind:
    if metric in instant_metrics:
        return "instant"
    form_type = _base_form(fact.form_type)
    if form_type in {"10-K", "20-F"} or fact.fiscal_period == "FY":
        return "annual"
    result: PeriodKind = "unknown"
    # SEC frames identify a discrete quarter. Q1 is also discrete when the
    # issuer omits frame; Q2/Q3 facts without a frame are commonly YTD and
    # must not be mislabeled as standalone quarters.
    if form_type == "10-Q" and (
        (fact.frame is not None and "Q" in fact.frame)
        or fact.fiscal_period == "Q1"
    ):
        result = "quarter"
    elif form_type == "10-Q" and fact.fiscal_period in {"Q2", "Q3"}:
        result = "year_to_date"
    elif form_type == "6-K" and fact.period_start and fact.period_end:
        duration_days = (fact.period_end - fact.period_start).days
        if duration_days <= 120:
            result = "quarter"
        elif duration_days < 330:
            result = "year_to_date"
    return result


def _is_usable(fact: FactValue, as_of: date | None) -> bool:
    if fact.period_end is None or _base_form(fact.form_type) not in {
        "10-K",
        "10-Q",
        "20-F",
        "6-K",
    }:
        return False
    return not (as_of and fact.filed_at and fact.filed_at > as_of)


def _dedupe_facts(
    facts: Iterable[FactValue],
    metric: str,
    instant_metrics: set[str] = INSTANT_METRICS,
    restatement_policy: RestatementPolicy = "latest_known",
) -> list[FactValue]:
    """Keep the latest filed value for an equivalent reported period."""
    selected: dict[tuple[date, str], FactValue] = {}
    for fact in facts:
        if fact.period_end is None:
            continue
        key = (
            fact.period_end,
            _period_kind(fact, metric, instant_metrics),
        )
        current = selected.get(key)
        if restatement_policy == "amended_only" and not (
            fact.form_type and fact.form_type.endswith("/A")
        ):
            continue
        replace = current is None
        if current is not None and restatement_policy == "original":
            replace = (fact.filed_at or date.max) < (current.filed_at or date.max)
        elif current is not None:
            replace = (fact.filed_at or date.min) > (current.filed_at or date.min)
        if replace:
            selected[key] = fact
    return sorted(selected.values(), key=lambda item: item.period_end or date.min)


class FinancialSnapshotBuilder:
    """Normalize common financial metrics from an SEC companyfacts payload."""

    def __init__(
        self,
        industry_template: str = "general",
        *,
        metric_template: MetricTemplate | None = None,
        restatement_policy: RestatementPolicy = "latest_known",
    ) -> None:
        if restatement_policy not in {"latest_known", "original", "amended_only"}:
            raise ValueError(f"unsupported restatement policy: {restatement_policy}")
        self.metric_template = metric_template or load_metric_template(industry_template)
        self._instant_metrics = self.metric_template.instant_metrics | {"total_debt"}
        self._ttm_metrics = self.metric_template.ttm_metrics | {"free_cash_flow"}
        self.restatement_policy = restatement_policy

    def build(
        self,
        *,
        ticker: str,
        cik: str,
        facts: dict,
        company_name: str | None = None,
        as_of: date | None = None,
    ) -> FinancialSnapshot:
        points: list[FinancialMetricPoint] = []
        warnings: list[str] = []

        for metric, definition in self.metric_template.metrics.items():
            extracted: list[FactValue] = []
            for concept in definition.concepts:
                candidate = [
                    item
                    for item in extract_metric(
                        facts,
                        concept=concept,
                        unit=definition.unit,
                    )
                    if _is_usable(item, as_of)
                ]
                if candidate:
                    extracted.extend(candidate)
            if not extracted:
                warnings.append(f"missing_metric:{metric}")
                continue
            points.extend(
                self._to_point(metric, fact.concept, fact)
                for fact in _dedupe_facts(
                    extracted,
                    metric,
                    self._instant_metrics,
                    self.restatement_policy,
                )
            )

        points.extend(self._derive_discrete_quarters(points))
        points.extend(self._derive_total_debt(points))
        points.extend(self._derive_free_cash_flow(points))
        points.extend(self._derive_ttm(points))
        points.extend(self._derive_margins(points))
        points = sorted(points, key=lambda point: (point.period_end, point.metric))
        return FinancialSnapshot(
            ticker=ticker.upper().strip(),
            cik=str(cik).zfill(10),
            company_name=company_name,
            as_of=(
                datetime.combine(as_of, time.min, tzinfo=UTC)
                if as_of
                else datetime.now(UTC)
            ),
            metrics=points,
            changes=self._derive_changes(points),
            warnings=warnings,
        )

    def _to_point(
        self,
        metric: str,
        concept: str,
        fact: FactValue,
    ) -> FinancialMetricPoint:
        assert fact.period_end is not None
        return FinancialMetricPoint(
            metric=metric,
            value=fact.value,
            unit=fact.unit,
            period_end=fact.period_end,
            period_start=fact.period_start,
            period_kind=_period_kind(fact, metric, self._instant_metrics),
            fiscal_year=fact.fiscal_year,
            fiscal_period=fact.fiscal_period,
            form_type=fact.form_type,
            accession_number=fact.accession_number,
            filed_at=fact.filed_at,
            source_concept=concept,
            source_accession_numbers=(
                [fact.accession_number] if fact.accession_number else []
            ),
        )

    def _derive_discrete_quarters(
        self,
        points: list[FinancialMetricPoint],
    ) -> list[FinancialMetricPoint]:
        """Convert reported YTD flows into discrete Q2/Q3 and derive Q4."""
        derived: list[FinancialMetricPoint] = []
        existing_quarters = {
            (point.metric, point.period_end)
            for point in points
            if point.period_kind == "quarter"
        }
        flow_points = [
            point
            for point in points
            if point.metric not in self._instant_metrics
            and point.metric not in SHARE_METRICS
            and point.period_start is not None
        ]
        groups: dict[tuple[str, date], list[FinancialMetricPoint]] = {}
        for point in flow_points:
            assert point.period_start is not None
            groups.setdefault((point.metric, point.period_start), []).append(point)

        for (_metric, _period_start), group in groups.items():
            quarters = {
                point.fiscal_period: point
                for point in group
                if point.period_kind == "quarter"
            }
            ytd = {
                point.fiscal_period: point
                for point in group
                if point.period_kind == "year_to_date"
            }
            for fiscal_period, prior_period in (("Q2", "Q1"), ("Q3", "Q2")):
                current_ytd = ytd.get(fiscal_period)
                if (
                    fiscal_period in quarters
                    or current_ytd is None
                    or (current_ytd.metric, current_ytd.period_end)
                    in existing_quarters
                ):
                    continue
                current = current_ytd
                if prior_period == "Q1":
                    prior = quarters.get("Q1")
                else:
                    prior = ytd.get("Q2")
                if prior is None:
                    continue
                derived.append(
                    FinancialSnapshotBuilder._difference_point(
                        current,
                        prior,
                        fiscal_period,
                        f"{fiscal_period} YTD - {prior_period} cumulative",
                    )
                )

            annual = next(
                (point for point in group if point.period_kind == "annual"),
                None,
            )
            if (
                annual
                and "Q4" not in quarters
                and "Q3" in ytd
                and (annual.metric, annual.period_end) not in existing_quarters
            ):
                derived.append(
                    FinancialSnapshotBuilder._difference_point(
                        annual,
                        ytd["Q3"],
                        "Q4",
                        "FY - Q3 YTD",
                    )
                )
        return derived

    @staticmethod
    def _difference_point(
        current: FinancialMetricPoint,
        prior: FinancialMetricPoint,
        fiscal_period: str,
        formula: str,
    ) -> FinancialMetricPoint:
        sources = sorted(
            set(current.source_accession_numbers + prior.source_accession_numbers)
        )
        return current.model_copy(
            update={
                "value": current.value - prior.value,
                "period_start": None,
                "period_kind": "quarter",
                "fiscal_period": fiscal_period,
                "source_concept": "derived",
                "status": "derived",
                "derivation": formula,
                "source_accession_numbers": sources,
            }
        )

    @staticmethod
    def _derive_free_cash_flow(points: list[FinancialMetricPoint]) -> list[FinancialMetricPoint]:
        by_key = {
            (point.metric, point.period_end, point.period_kind): point
            for point in points
        }
        derived: list[FinancialMetricPoint] = []
        for point in points:
            if point.metric != "operating_cash_flow":
                continue
            capex = by_key.get(("capital_expenditure", point.period_end, point.period_kind))
            if capex is None:
                continue
            derived.append(
                point.model_copy(
                    update={
                        "metric": "free_cash_flow",
                        "value": point.value - abs(capex.value),
                        "source_concept": "derived",
                        "status": "derived",
                        "derivation": "operating_cash_flow - abs(capital_expenditure)",
                        "source_accession_numbers": sorted(
                            set(
                                point.source_accession_numbers
                                + capex.source_accession_numbers
                            )
                        ),
                    }
                )
            )
        return derived

    @staticmethod
    def _derive_total_debt(
        points: list[FinancialMetricPoint],
    ) -> list[FinancialMetricPoint]:
        components = {
            (point.metric, point.period_end): point
            for point in points
            if point.metric in {"current_debt", "long_term_debt"}
        }
        period_ends = {
            point.period_end
            for point in points
            if point.metric in {"current_debt", "long_term_debt"}
        }
        derived: list[FinancialMetricPoint] = []
        for period_end in period_ends:
            current = components.get(("current_debt", period_end))
            long_term = components.get(("long_term_debt", period_end))
            if current is None or long_term is None:
                continue
            derived.append(
                long_term.model_copy(
                    update={
                        "metric": "total_debt",
                        "value": current.value + long_term.value,
                        "source_concept": "derived",
                        "status": "derived",
                        "derivation": "current_debt + long_term_debt",
                        "source_accession_numbers": sorted(
                            set(
                                current.source_accession_numbers
                                + long_term.source_accession_numbers
                            )
                        ),
                    }
                )
            )
        return derived

    def _derive_ttm(
        self,
        points: list[FinancialMetricPoint],
    ) -> list[FinancialMetricPoint]:
        derived: list[FinancialMetricPoint] = []
        for metric in self._ttm_metrics:
            quarters = sorted(
                (
                    point
                    for point in points
                    if point.metric == metric and point.period_kind == "quarter"
                ),
                key=lambda point: point.period_end,
            )
            for index in range(3, len(quarters)):
                window = quarters[index - 3 : index + 1]
                if (
                    len({point.period_end for point in window}) != 4
                    or any(
                        not _is_next_quarter(previous, current)
                        for previous, current in pairwise(window)
                    )
                ):
                    continue
                latest = window[-1]
                sources = sorted(
                    {
                        accession
                        for point in window
                        for accession in point.source_accession_numbers
                    }
                )
                derived.append(
                    latest.model_copy(
                        update={
                            "value": sum(point.value for point in window),
                            "period_start": window[0].period_start,
                            "period_kind": "ttm",
                            "source_concept": "derived",
                            "status": "derived",
                            "derivation": "sum of latest four discrete quarters",
                            "source_accession_numbers": sources,
                        }
                    )
                )
        return derived

    @staticmethod
    def _derive_margins(
        points: list[FinancialMetricPoint],
    ) -> list[FinancialMetricPoint]:
        revenue_by_period = {
            (point.period_end, point.period_kind): point
            for point in points
            if point.metric == "revenue" and point.value != 0
        }
        derived: list[FinancialMetricPoint] = []
        for point in points:
            margin_metric = MARGIN_METRICS.get(point.metric)
            if margin_metric is None:
                continue
            revenue = revenue_by_period.get((point.period_end, point.period_kind))
            if revenue is None:
                continue
            derived.append(
                point.model_copy(
                    update={
                        "metric": margin_metric,
                        "value": point.value / revenue.value,
                        "unit": "ratio",
                        "source_concept": "derived",
                        "status": "derived",
                        "derivation": f"{point.metric} / revenue",
                        "source_accession_numbers": sorted(
                            set(
                                point.source_accession_numbers
                                + revenue.source_accession_numbers
                            )
                        ),
                    }
                )
            )
        return derived

    @staticmethod
    def _derive_changes(
        points: list[FinancialMetricPoint],
    ) -> list[FinancialChange]:
        changes: list[FinancialChange] = []
        metrics = {point.metric for point in points}
        for metric in metrics:
            quarters = sorted(
                (
                    point
                    for point in points
                    if point.metric == metric and point.period_kind == "quarter"
                ),
                key=lambda point: point.period_end,
            )
            for previous, current in pairwise(quarters):
                if _is_next_quarter(previous, current):
                    changes.append(
                        FinancialSnapshotBuilder._change(current, previous, "qoq")
                    )
            for current in quarters:
                comparable = [
                    previous
                    for previous in quarters
                    if previous.period_end < current.period_end
                    and _is_year_apart(previous, current)
                ]
                if comparable:
                    previous = min(
                        comparable,
                        key=lambda point: abs(
                            (current.period_end - point.period_end).days - 365
                        ),
                    )
                    changes.append(
                        FinancialSnapshotBuilder._change(current, previous, "yoy")
                    )

            ttm = sorted(
                (
                    point
                    for point in points
                    if point.metric == metric and point.period_kind == "ttm"
                ),
                key=lambda point: point.period_end,
            )
            for index in range(4, len(ttm)):
                previous = ttm[index - 4]
                current = ttm[index]
                if _is_year_apart(previous, current):
                    changes.append(
                        FinancialSnapshotBuilder._change(
                            current,
                            previous,
                            "ttm_yoy",
                        )
                    )

            annual = sorted(
                (
                    point
                    for point in points
                    if point.metric == metric and point.period_kind == "annual"
                ),
                key=lambda point: point.period_end,
            )
            for previous, current in pairwise(annual):
                if _is_year_apart(previous, current):
                    changes.append(
                        FinancialSnapshotBuilder._change(
                            current,
                            previous,
                            "annual_yoy",
                        )
                    )
        return sorted(
            changes,
            key=lambda item: (item.current_period_end, item.metric, item.change_type),
        )

    @staticmethod
    def _change(
        current: FinancialMetricPoint,
        previous: FinancialMetricPoint,
        change_type: ChangeType,
    ) -> FinancialChange:
        absolute = current.value - previous.value
        percent = absolute / abs(previous.value) if previous.value != 0 else None
        return FinancialChange(
            metric=current.metric,
            change_type=change_type,
            current_period_end=current.period_end,
            comparison_period_end=previous.period_end,
            current_value=current.value,
            comparison_value=previous.value,
            absolute_change=absolute,
            percent_change=percent,
            unit=current.unit,
            source_accession_numbers=sorted(
                set(
                    current.source_accession_numbers
                    + previous.source_accession_numbers
                )
            ),
        )
