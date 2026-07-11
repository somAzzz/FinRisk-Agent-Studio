from __future__ import annotations

from datetime import date

import pytest

from src.research.financial_snapshot import (
    FinancialSnapshotBuilder,
    merge_company_facts,
)


def _concept(rows: list[dict]) -> dict:
    return {"units": {"USD": rows}}


def test_builds_normalized_periods_and_free_cash_flow() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-03-31",
                        "val": 100, "form": "10-Q", "filed": "2023-05-01",
                        "fy": 2023, "fp": "Q1", "frame": "CY2023Q1", "accn": "a1",
                    },
                    {
                        "start": "2023-01-01", "end": "2023-12-31",
                        "val": 500, "form": "10-K", "filed": "2024-02-01",
                        "fy": 2023, "fp": "FY", "frame": "CY2023", "accn": "a2",
                    },
                ]),
                "NetCashProvidedByUsedInOperatingActivities": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-12-31",
                        "val": 80, "form": "10-K", "filed": "2024-02-01",
                        "fy": 2023, "fp": "FY", "frame": "CY2023", "accn": "a2",
                    },
                ]),
                "PaymentsToAcquirePropertyPlantAndEquipment": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-12-31",
                        "val": 20, "form": "10-K", "filed": "2024-02-01",
                        "fy": 2023, "fp": "FY", "frame": "CY2023", "accn": "a2",
                    },
                ]),
            }
        }
    }

    snapshot = FinancialSnapshotBuilder().build(
        ticker="test",
        cik="123",
        facts=facts,
        company_name="Test Corp",
    )

    revenue = snapshot.series("revenue")
    assert [point.period_kind for point in revenue] == ["quarter", "annual"]
    assert snapshot.series("free_cash_flow")[0].value == 60
    assert snapshot.series("free_cash_flow")[0].status == "derived"
    assert snapshot.cik == "0000000123"


def test_respects_as_of_and_prefers_latest_filed_duplicate() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-12-31", "val": 90,
                        "form": "10-K", "filed": "2024-01-20", "fp": "FY",
                        "accn": "original",
                    },
                    {
                        "start": "2023-01-01", "end": "2023-12-31", "val": 100,
                        "form": "10-K", "filed": "2024-02-20", "fp": "FY",
                        "accn": "amended",
                    },
                    {
                        "start": "2024-01-01", "end": "2024-12-31", "val": 120,
                        "form": "10-K", "filed": "2025-02-01", "fp": "FY",
                        "accn": "future",
                    },
                ])
            }
        }
    }

    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="123",
        facts=facts,
        as_of=date(2024, 12, 31),
    )
    revenue = snapshot.series("revenue")
    assert len(revenue) == 1
    assert revenue[0].value == 100
    assert revenue[0].accession_number == "amended"


def test_preserves_missing_metrics_as_explicit_warnings() -> None:
    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="123",
        facts={"facts": {}},
    )
    assert snapshot.metrics == []
    assert "missing_metric:revenue" in snapshot.warnings
    assert "missing_metric:cash" in snapshot.warnings
    assert "missing_metric:long_term_debt" in snapshot.warnings


def test_supports_ifrs_20f_and_discrete_6k_facts() -> None:
    facts = {
        "facts": {
            "ifrs-full": {
                "Revenue": _concept(
                    [
                        {
                            "start": "2024-01-01", "end": "2024-12-31",
                            "val": 1000, "form": "20-F", "filed": "2025-04-17",
                            "fy": 2024, "fp": "FY", "accn": "20f",
                        },
                        {
                            "start": "2025-01-01", "end": "2025-03-31",
                            "val": 300, "form": "6-K", "filed": "2025-04-30",
                            "accn": "6k-q1",
                        },
                        {
                            "start": "2025-01-01", "end": "2025-06-30",
                            "val": 650, "form": "6-K", "filed": "2025-07-31",
                            "accn": "6k-ytd",
                        },
                    ]
                ),
                "ProfitLossFromOperatingActivities": _concept(
                    [{
                        "start": "2024-01-01", "end": "2024-12-31",
                        "val": 300, "form": "20-F", "filed": "2025-04-17",
                        "fy": 2024, "fp": "FY", "accn": "20f",
                    }]
                ),
            }
        }
    }

    snapshot = FinancialSnapshotBuilder().build(
        ticker="FPI", cik="123", facts=facts,
    )

    assert snapshot.series("revenue", "annual")[0].value == 1000
    assert snapshot.series("revenue", "quarter")[0].value == 300
    assert snapshot.series("revenue", "year_to_date")[0].value == 650
    assert snapshot.series("operating_income", "annual")[0].value == 300


def test_merges_concept_alias_history_and_derives_total_debt() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept([
                    {
                        "start": "2024-01-01", "end": "2024-12-31", "val": 120,
                        "form": "10-K", "filed": "2025-02-01", "fy": 2024,
                        "fp": "FY", "accn": "new-revenue",
                    }
                ]),
                "Revenues": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-12-31", "val": 100,
                        "form": "10-K", "filed": "2024-02-01", "fy": 2023,
                        "fp": "FY", "accn": "old-revenue",
                    }
                ]),
                "LongTermDebtCurrent": _concept([
                    {
                        "end": "2024-12-31", "val": 10, "form": "10-K",
                        "filed": "2025-02-01", "fy": 2024, "fp": "FY",
                        "accn": "debt-filing",
                    }
                ]),
                "LongTermDebtNoncurrent": _concept([
                    {
                        "end": "2024-12-31", "val": 40, "form": "10-K",
                        "filed": "2025-02-01", "fy": 2024, "fp": "FY",
                        "accn": "debt-filing",
                    }
                ]),
            }
        }
    }

    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="123",
        facts=facts,
    )

    assert [point.value for point in snapshot.series("revenue", "annual")] == [
        100, 120,
    ]
    total_debt = snapshot.series("total_debt", "instant")
    assert total_debt[0].value == 50
    assert total_debt[0].derivation == "current_debt + long_term_debt"


def test_converts_ytd_to_quarters_and_builds_ttm_and_changes() -> None:
    revenue_rows = [
        {
            "start": "2023-01-01", "end": "2023-03-31", "val": 100,
            "form": "10-Q", "filed": "2023-05-01", "fy": 2023,
            "fp": "Q1", "frame": "CY2023Q1", "accn": "23q1",
        },
        {
            "start": "2023-01-01", "end": "2023-06-30", "val": 220,
            "form": "10-Q", "filed": "2023-08-01", "fy": 2023,
            "fp": "Q2", "accn": "23q2",
        },
        {
            "start": "2023-01-01", "end": "2023-09-30", "val": 360,
            "form": "10-Q", "filed": "2023-11-01", "fy": 2023,
            "fp": "Q3", "accn": "23q3",
        },
        {
            "start": "2023-01-01", "end": "2023-12-31", "val": 500,
            "form": "10-K", "filed": "2024-02-01", "fy": 2023,
            "fp": "FY", "frame": "CY2023", "accn": "23fy",
        },
        {
            "start": "2024-01-01", "end": "2024-03-31", "val": 110,
            "form": "10-Q", "filed": "2024-05-01", "fy": 2024,
            "fp": "Q1", "frame": "CY2024Q1", "accn": "24q1",
        },
        {
            "start": "2024-01-01", "end": "2024-06-30", "val": 240,
            "form": "10-Q", "filed": "2024-08-01", "fy": 2024,
            "fp": "Q2", "accn": "24q2",
        },
        {
            "start": "2024-01-01", "end": "2024-09-30", "val": 390,
            "form": "10-Q", "filed": "2024-11-01", "fy": 2024,
            "fp": "Q3", "accn": "24q3",
        },
        {
            "start": "2024-01-01", "end": "2024-12-31", "val": 550,
            "form": "10-K", "filed": "2025-02-01", "fy": 2024,
            "fp": "FY", "frame": "CY2024", "accn": "24fy",
        },
    ]
    gross_profit_rows = [
        {**row, "val": value}
        for row, value in zip(revenue_rows[:4], [40, 90, 150, 220], strict=True)
    ]
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": _concept(revenue_rows),
                "GrossProfit": _concept(gross_profit_rows),
            }
        }
    }

    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="123",
        facts=facts,
    )

    quarters = snapshot.series("revenue", "quarter")
    assert [point.fiscal_period for point in quarters] == [
        "Q1", "Q2", "Q3", "Q4", "Q1", "Q2", "Q3", "Q4",
    ]
    assert [point.value for point in quarters[:4]] == [100, 120, 140, 140]
    assert quarters[1].derivation == "Q2 YTD - Q1 cumulative"
    assert quarters[3].source_accession_numbers == ["23fy", "23q3"]

    ttm = snapshot.series("revenue", "ttm")
    assert [point.value for point in ttm] == [500, 510, 520, 530, 550]
    assert snapshot.series("gross_margin", "ttm")[0].value == 0.44

    revenue_yoy = [
        change
        for change in snapshot.changes
        if change.metric == "revenue" and change.change_type == "yoy"
    ]
    assert len(revenue_yoy) == 4
    q1_yoy = next(
        change
        for change in revenue_yoy
        if change.current_period_end.isoformat() == "2024-03-31"
    )
    assert q1_yoy.percent_change == 0.1
    assert q1_yoy.source_accession_numbers == ["23q1", "24q1"]
    ttm_yoy = [
        change
        for change in snapshot.changes
        if change.metric == "revenue" and change.change_type == "ttm_yoy"
    ]
    assert len(ttm_yoy) == 1
    assert ttm_yoy[0].percent_change == 0.1


def test_does_not_label_nonconsecutive_quarters_as_qoq_or_ttm() -> None:
    rows = [
        {
            "start": "2023-01-01", "end": "2023-03-31", "val": 100,
            "form": "10-Q", "filed": "2023-05-01", "fy": 2023,
            "fp": "Q1", "frame": "CY2023Q1", "accn": "23q1",
        },
        {
            "start": "2024-01-01", "end": "2024-03-31", "val": 110,
            "form": "10-Q", "filed": "2024-05-01", "fy": 2024,
            "fp": "Q1", "frame": "CY2024Q1", "accn": "24q1",
        },
        {
            "start": "2024-04-01", "end": "2024-06-30", "val": 120,
            "form": "10-Q", "filed": "2024-08-01", "fy": 2024,
            "fp": "Q2", "frame": "CY2024Q2", "accn": "24q2",
        },
        {
            "start": "2024-07-01", "end": "2024-09-30", "val": 130,
            "form": "10-Q", "filed": "2024-11-01", "fy": 2024,
            "fp": "Q3", "frame": "CY2024Q3", "accn": "24q3",
        },
    ]
    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="123",
        facts={"facts": {"us-gaap": {"Revenues": _concept(rows)}}},
    )

    assert snapshot.series("revenue", "ttm") == []
    qoq = [
        change for change in snapshot.changes if change.change_type == "qoq"
    ]
    assert len(qoq) == 2


def test_merges_current_and_predecessor_company_facts() -> None:
    current = {
        "facts": {"custom": {"HoldingCompanyFact": _concept([])}}
    }
    predecessor = {
        "facts": {
            "us-gaap": {
                "Revenues": _concept([
                    {
                        "start": "2023-01-01", "end": "2023-12-31",
                        "val": 100, "form": "10-K", "filed": "2024-02-01",
                        "fy": 2023, "fp": "FY", "accn": "predecessor",
                    }
                ])
            }
        }
    }
    snapshot = FinancialSnapshotBuilder().build(
        ticker="TST",
        cik="new-cik",
        facts=merge_company_facts(current, predecessor),
    )
    assert snapshot.series("revenue", "annual")[0].accession_number == (
        "predecessor"
    )


def test_loads_industry_metrics_and_productive_asset_capex_alias() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "InventoryNet": _concept([
                    {
                        "end": "2025-01-31", "val": 11, "form": "10-K",
                        "filed": "2025-03-01", "fy": 2025, "fp": "FY",
                        "accn": "fy",
                    }
                ]),
                "PaymentsToAcquireProductiveAssets": _concept([
                    {
                        "start": "2024-02-01", "end": "2025-01-31",
                        "val": 7, "form": "10-K", "filed": "2025-03-01",
                        "fy": 2025, "fp": "FY", "accn": "fy",
                    }
                ]),
            }
        }
    }

    snapshot = FinancialSnapshotBuilder("semiconductor").build(
        ticker="CHIP",
        cik="123",
        facts=facts,
    )

    assert snapshot.series("inventory", "instant")[0].value == 11
    assert snapshot.series("capital_expenditure", "annual")[0].value == 7
    assert snapshot.series("productive_asset_capex", "annual")[0].value == 7
    assert "missing_metric:inventory" not in snapshot.warnings


def test_rejects_unknown_industry_template() -> None:
    with pytest.raises(ValueError, match="unknown financial metric template"):
        FinancialSnapshotBuilder("not_a_real_industry")
