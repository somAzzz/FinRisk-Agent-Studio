from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.research.expectations import (
    ExpectationPoint,
    ExpectationStore,
    compare_expectation_to_actual,
)
from src.research.models import FinancialMetricPoint


def _expectation() -> ExpectationPoint:
    return ExpectationPoint(
        ticker="acme",
        metric="revenue",
        fiscal_period="2026Q1",
        value=100,
        unit="USD",
        source="personal model",
        observed_at=datetime(2026, 3, 1, tzinfo=UTC),
        as_of=datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_csv_import_is_idempotent_and_preserves_history(tmp_path) -> None:
    store = ExpectationStore(tmp_path / "expectations.sqlite")
    content = """ticker,metric,fiscal_period,value,unit,source,observed_at,as_of,notes
ACME,revenue,2026Q1,100,USD,personal model,2026-03-01T00:00:00Z,2026-03-01T00:00:00Z,base case
"""

    first = store.import_csv(content)
    second = store.import_csv(content)

    assert first.imported == 1
    assert second.imported == 0
    assert second.skipped == 1
    assert len(store.list(ticker="ACME")) == 1


def test_csv_import_rejects_missing_columns_and_bad_rows(tmp_path) -> None:
    store = ExpectationStore(tmp_path / "expectations.sqlite")
    with pytest.raises(ValueError, match="missing required columns"):
        store.import_csv("ticker,value\nACME,1\n")
    with pytest.raises(ValueError, match="invalid CSV row 2"):
        store.import_csv(
            "ticker,metric,fiscal_period,value,unit,source,observed_at,as_of\n"
            "ACME,revenue,2026Q1,nope,USD,model,2026-03-01,2026-03-01\n"
        )


def test_surprise_rejects_post_filing_expectation() -> None:
    actual = FinancialMetricPoint(
        metric="revenue",
        value=110,
        unit="USD",
        period_end=date(2026, 3, 31),
        fiscal_year=2026,
        fiscal_period="Q1",
        filed_at=date(2026, 4, 20),
        source_concept="Revenue",
    )
    comparison = compare_expectation_to_actual(_expectation(), actual)
    assert comparison.absolute_surprise == 10
    assert comparison.percent_surprise == pytest.approx(0.1)

    revised = _expectation().model_copy(update={"as_of": datetime(2026, 4, 21, tzinfo=UTC)})
    with pytest.raises(ValueError, match="known before"):
        compare_expectation_to_actual(revised, actual)


def test_expectation_requires_point_in_time_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ExpectationPoint.model_validate(
            {
                **_expectation().model_dump(),
                "as_of": datetime(2026, 3, 1),
            }
        )
