from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.research.change_detection import ResearchChange, ResearchChangeSet
from src.research.comparison import (
    build_research_queue,
    compare_company_snapshots,
)
from src.research.models import (
    CompanyResearchSnapshot,
    FinancialMetricPoint,
    FinancialSnapshot,
)


def _snapshot(ticker: str, *, currency: str = "USD") -> CompanyResearchSnapshot:
    return CompanyResearchSnapshot(
        snapshot_id=f"snapshot-{ticker}",
        ticker=ticker,
        period="2026Q1",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        source_fingerprint=f"fingerprint-{ticker}",
        financials=FinancialSnapshot(
            ticker=ticker,
            cik=ticker,
            currency=currency,
            as_of=datetime(2026, 4, 30, tzinfo=UTC),
            metrics=[
                FinancialMetricPoint(
                    metric="revenue",
                    value=100 if ticker == "AAA" else 200,
                    unit=currency,
                    period_end=date(2026, 3, 31),
                    period_kind="ttm",
                    source_concept="Revenue",
                    accession_number=f"filing-{ticker}",
                )
            ],
        ),
    )


def test_company_comparison_uses_same_as_of_and_preserves_evidence() -> None:
    response = compare_company_snapshots(
        [_snapshot("AAA"), _snapshot("BBB")],
        metrics=["revenue", "free_cash_flow"],
        period_kind="ttm",
    )

    revenue = [item for item in response.values if item.metric == "revenue"]
    assert [item.value for item in revenue] == [100, 200]
    assert revenue[0].evidence_ids == ["filing-AAA"]
    assert all(item.status == "not_available" for item in response.values if item.metric == "free_cash_flow")
    assert "not a ranking" in response.disclaimer


def test_company_comparison_marks_currency_mismatch_not_comparable() -> None:
    response = compare_company_snapshots(
        [_snapshot("AAA"), _snapshot("BBB", currency="EUR")],
        metrics=["revenue"],
        period_kind="ttm",
    )
    assert all(item.status == "not_comparable" for item in response.values)

    with pytest.raises(ValueError, match="same as_of"):
        compare_company_snapshots(
            [
                _snapshot("AAA"),
                _snapshot("BBB").model_copy(update={"as_of": datetime(2026, 5, 1, tzinfo=UTC)}),
            ],
            metrics=["revenue"],
            period_kind="ttm",
        )


def test_peer_comparison_exposes_snapshot_freshness() -> None:
    stale = _snapshot("AAA").model_copy(
        update={"as_of": datetime(2026, 4, 20, tzinfo=UTC)}
    )
    current = _snapshot("BBB")

    response = compare_company_snapshots(
        [stale, current],
        metrics=["revenue"],
        period_kind="ttm",
        strict_as_of=False,
    )

    values = {item.ticker: item for item in response.values}
    assert values["AAA"].freshness_days == 10
    assert values["BBB"].freshness_days == 0
    assert response.as_of == "2026-04-30"


def test_research_queue_orders_evidence_review_not_investment_scores() -> None:
    high = ResearchChange(
        change_id="high",
        ticker="AAA",
        category="financial",
        key="revenue",
        status="weakened",
        materiality="high",
        after_evidence_ids=["filing-AAA"],
        detection_method="test",
        explanation="Revenue changed",
        confidence=1,
    )
    medium = ResearchChange(
        change_id="medium",
        ticker="BBB",
        category="guidance",
        key="guidance",
        status="persistent",
        materiality="medium",
        after_evidence_ids=["transcript-BBB"],
        detection_method="test",
        explanation="Guidance changed",
        confidence=1,
    )
    queue = build_research_queue(
        [
            ResearchChangeSet(ticker="BBB", from_snapshot_id="1", to_snapshot_id="2", changes=[medium]),
            ResearchChangeSet(ticker="AAA", from_snapshot_id="1", to_snapshot_id="2", changes=[high]),
        ]
    )
    assert [item.ticker for item in queue.entries] == ["AAA", "BBB"]
    assert queue.entries[0].priority == "high"
    assert "not an investment score" in queue.disclaimer
