from __future__ import annotations

from src.research.valuation_store import ValuationAssumptionStore


def test_valuation_assumption_history_is_immutable_and_ticker_scoped(tmp_path) -> None:
    store = ValuationAssumptionStore(tmp_path / "research.sqlite")

    first = store.save(
        ticker="ACME",
        kind="multiple",
        request={"method": "pe", "earnings": 10},
        result={"value": 20},
        evidence_ids=["filing", "filing"],
    )
    second = store.save(
        ticker="ACME",
        kind="dcf",
        request={"wacc": 0.1},
        result={"value": 25},
        evidence_ids=["model"],
    )
    store.save(
        ticker="OTHER",
        kind="multiple",
        request={},
        result={},
        evidence_ids=[],
    )

    history = store.list("acme")
    assert {item.assumption_snapshot_id for item in history} == {
        first.assumption_snapshot_id,
        second.assumption_snapshot_id,
    }
    assert first.evidence_ids == ["filing"]
