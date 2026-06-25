"""Tests for :func:`fetch_financial_metrics_defeatbeta` and
:func:`fetch_revenue_breakdown_defeatbeta`.

Defeatbeta's ratio endpoints return time-series DataFrames. We stub the
``Ticker`` factory with a fake that returns canned rows.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.data.providers.defeatbeta import (
    fetch_financial_metrics_defeatbeta,
    fetch_revenue_breakdown_defeatbeta,
)
from src.data.transcripts import TranscriptProviderConfigError


class FakeDataFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.empty = len(rows) == 0

    def to_dict(self, _orient: str = "records") -> list[dict[str, Any]]:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeTicker:
    def __init__(
        self,
        ratios: dict[str, list[dict[str, Any]]] | None = None,
        revenue: list[dict[str, Any]] | None = None,
        raise_on: set[str] | None = None,
    ) -> None:
        self._ratios = ratios or {}
        self._revenue = revenue or []
        self._raise_on = raise_on or set()

    def __getattr__(self, name: str) -> Any:
        # Only ratio methods and revenue methods are routed here.
        if name in self._ratios:

            def fn() -> FakeDataFrame:
                if name in self._raise_on:
                    raise RuntimeError(f"upstream error on {name}")
                return FakeDataFrame(self._ratios[name])

            return fn
        if name.startswith("revenue_by_"):
            if "revenue_by_segment" in self._raise_on:
                raise RuntimeError("binder error")
            return lambda: FakeDataFrame(self._revenue)
        raise AttributeError(name)


def _install_fake_ticker(
    monkeypatch: pytest.MonkeyPatch,
    ticker: FakeTicker,
) -> None:
    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", lambda *_a, **_kw: ticker)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", None)


def _ttm_pe_rows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "AAPL",
            "report_date": "2024-01-02",
            "eps_report_date": "2023-09-30",
            "close_price": 187.15,
            "ttm_eps": 6.16,
            "ttm_pe": 30.4,
        },
        {
            "symbol": "AAPL",
            "report_date": "2026-06-24",
            "eps_report_date": "2026-03-31",
            "close_price": 293.08,
            "ttm_eps": 8.27,
            "ttm_pe": 35.45,
        },
    ]


def _roic_rows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "AAPL",
            "report_date": "2024-09-30",
            "ebit": 125000,
            "tax_rate_for_calcs": 0.18,
            "nopat": 102500,
            "beginning_invested_capital": 130000,
            "ending_invested_capital": 140000,
            "avg_invested_capital": 135000,
            "roic": 0.506,
        },
        {
            "symbol": "AAPL",
            "report_date": "2025-09-30",
            "ebit": 130000,
            "tax_rate_for_calcs": 0.18,
            "nopat": 106600,
            "beginning_invested_capital": 140000,
            "ending_invested_capital": 150000,
            "avg_invested_capital": 145000,
            "roic": 0.521,
        },
    ]


def _revenue_rows() -> list[dict[str, Any]]:
    return [
        {
            "breakdown": "Geography",
            "breakdown_name": "Americas",
            "value_type": "absolute",
            "period_type": "quarterly",
            "report_date": "2024-03-30",
            "value": 37.3e9,
        },
        {
            "breakdown": "Geography",
            "breakdown_name": "Americas",
            "value_type": "percent",
            "period_type": "quarterly",
            "report_date": "2024-03-30",
            "value": 0.42,
        },
        {
            "breakdown": "Geography",
            "breakdown_name": "Europe",
            "value_type": "absolute",
            "period_type": "quarterly",
            "report_date": "2024-03-30",
            "value": 24.1e9,
        },
        {
            "breakdown": "Geography",
            "breakdown_name": "Greater China",
            "value_type": "absolute",
            "period_type": "trailing",
            "report_date": "2024-03-30",
            "value": 65.8e9,
        },
    ]


# --- fetch_financial_metrics_defeatbeta ----------------------------------


def test_metrics_takes_latest_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """The latest (last) row's value is selected per metric."""
    ticker = FakeTicker(
        ratios={
            "ttm_pe": _ttm_pe_rows(),
            "roic": _roic_rows(),
            "ps_ratio": [],  # empty → None
        }
    )
    _install_fake_ticker(monkeypatch, ticker)

    metrics = fetch_financial_metrics_defeatbeta("AAPL")

    # Latest TTM PE row's ttm_pe is 35.45.
    assert metrics["ttm_pe"] == pytest.approx(35.45)
    # Latest ROIC is 0.521.
    assert metrics["roic"] == pytest.approx(0.521)
    # ps_ratio has no rows → None.
    assert metrics["ps_ratio"] is None
    # WACC is not in _RATIO_METHODS → key absent. (We intentionally skip
    # it because of the 0.0.48 bug.)
    assert "wacc" not in metrics


def test_metrics_handles_nan_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """NaN values are skipped and earlier rows are consulted."""
    rows = _ttm_pe_rows() + [
        {
            "symbol": "AAPL",
            "report_date": "2026-06-25",
            "ttm_pe": float("nan"),
        }
    ]
    ticker = FakeTicker(ratios={"ttm_pe": rows})
    _install_fake_ticker(monkeypatch, ticker)

    metrics = fetch_financial_metrics_defeatbeta("AAPL")
    # Last non-NaN ttm_pe is the second-to-last row (35.45).
    assert metrics["ttm_pe"] == pytest.approx(35.45)


def test_metrics_partial_failure_returns_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If one ratio method raises, others still return values."""
    ticker = FakeTicker(
        ratios={
            "ttm_pe": _ttm_pe_rows(),
            "roe": _roic_rows(),  # values don't matter — roe column is "roe"
        },
        raise_on={"roe"},
    )
    _install_fake_ticker(monkeypatch, ticker)

    metrics = fetch_financial_metrics_defeatbeta("AAPL")
    assert metrics["ttm_pe"] == pytest.approx(35.45)
    assert metrics["roe"] is None  # raised → None


def test_metrics_dependency_missing_returns_none_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If defeatbeta-api is missing, every value is None."""
    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", None)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", ImportError("not installed"))

    def raise_config(*_a: Any, **_kw: Any) -> Any:
        raise TranscriptProviderConfigError("defeatbeta-api not available")

    monkeypatch.setattr(mod, "_ensure_defeatbeta", raise_config)

    metrics = fetch_financial_metrics_defeatbeta("AAPL")
    # All ratio keys are present with None values (graceful degradation).
    assert all(v is None for v in metrics.values())
    assert len(metrics) >= 5


# --- fetch_revenue_breakdown_defeatbeta ----------------------------------


def test_revenue_breakdown_filters_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``period_type`` filters rows; values are returned long-format."""
    ticker = FakeTicker(revenue=_revenue_rows())
    _install_fake_ticker(monkeypatch, ticker)

    rows = fetch_revenue_breakdown_defeatbeta("AAPL", breakdown="geography", period_type="quarterly")
    # Three quarterly rows (Americas absolute, Americas percent, Europe).
    assert len(rows) == 3
    for row in rows:
        assert row["breakdown"] == "Geography"
        assert row["period_type"] == "quarterly"


def test_revenue_breakdown_upstream_bug_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 0.0.48 binder error is swallowed and ``[]`` is returned."""
    ticker = FakeTicker(
        revenue=[],
        raise_on={"revenue_by_segment"},
    )
    _install_fake_ticker(monkeypatch, ticker)

    rows = fetch_revenue_breakdown_defeatbeta("AAPL", breakdown="segment")
    assert rows == []


def test_revenue_breakdown_dependency_missing_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing defeatbeta-api returns ``[]``."""
    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", None)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", ImportError("not installed"))

    def raise_config(*_a: Any, **_kw: Any) -> Any:
        raise TranscriptProviderConfigError("defeatbeta-api not available")

    monkeypatch.setattr(mod, "_ensure_defeatbeta", raise_config)

    assert fetch_revenue_breakdown_defeatbeta("AAPL") == []
