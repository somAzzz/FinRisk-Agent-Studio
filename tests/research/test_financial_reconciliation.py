from __future__ import annotations

from datetime import date

from src.research.financial_reconciliation import reconcile_financial_snapshot
from src.research.models import FinancialMetricPoint, FinancialSnapshot


def _reported(period_end: date, value: float, accession: str) -> FinancialMetricPoint:
    return FinancialMetricPoint(
        metric="revenue",
        value=value,
        unit="USD",
        period_end=period_end,
        period_start=date(period_end.year, 1, 1),
        period_kind="quarter",
        accession_number=accession,
        filed_at=date(period_end.year, 5, 1),
        source_concept="Revenues",
        source_accession_numbers=[accession],
    )


def test_reconciles_reported_lineage_and_ttm_formula() -> None:
    quarter_ends = [
        date(2024, 3, 31),
        date(2024, 6, 30),
        date(2024, 9, 30),
        date(2024, 12, 31),
    ]
    quarters = [
        _reported(period_end, value, f"q{index}")
        for index, (period_end, value) in enumerate(
            zip(quarter_ends, [10.0, 20.0, 30.0, 40.0], strict=True),
            start=1,
        )
    ]
    ttm = quarters[-1].model_copy(
        update={
            "value": 100.0,
            "period_kind": "ttm",
            "status": "derived",
            "source_concept": "derived",
            "derivation": "sum of latest four discrete quarters",
        }
    )
    snapshot = FinancialSnapshot(
        ticker="TST", cik="123", metrics=[*quarters, ttm]
    )
    rows = [
        {
            "end": point.period_end.isoformat(),
            "val": point.value,
            "form": "10-Q",
            "filed": point.filed_at.isoformat(),
            "accn": point.accession_number,
        }
        for point in quarters
    ]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rows}}}}}

    report = reconcile_financial_snapshot(
        snapshot,
        facts,
        metrics=["revenue"],
        expected_periods=4,
    )

    assert report.passed
    assert report.metrics[0].checked_points == 5


def test_distinguishes_allowed_na_from_failed_coverage() -> None:
    snapshot = FinancialSnapshot(ticker="TST", cik="123")

    report = reconcile_financial_snapshot(
        snapshot,
        {"facts": {}},
        metrics=["gross_profit", "revenue"],
        allowed_missing=["gross_profit"],
    )

    assert report.metrics[0].status == "not_applicable"
    assert report.metrics[1].status == "failed"
    assert report.passed is False
