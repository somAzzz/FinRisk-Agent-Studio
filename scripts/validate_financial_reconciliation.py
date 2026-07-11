"""Run the release financial reconciliation matrix against live SEC facts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from src.data.sec_client import SECClient
from src.data.ticker_resolver import TickerResolver
from src.research.financial_reconciliation import reconcile_financial_snapshot
from src.research.financial_snapshot import FinancialSnapshotBuilder, merge_company_facts

CORE_METRICS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "cash",
    "current_debt",
    "long_term_debt",
    "diluted_shares",
)
MATRIX = {
    "AAPL": {"template": "general", "allowed_missing": (), "periods": 12},
    "NVDA": {"template": "semiconductor", "allowed_missing": (), "periods": 12},
    "XOM": {
        "template": "energy",
        "allowed_missing": ("gross_profit", "operating_income"),
        "periods": 12,
    },
    "JPM": {
        "template": "bank",
        "allowed_missing": ("gross_profit", "operating_income", "cet1_ratio"),
        "periods": 12,
        "metrics": (
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "operating_cash_flow",
            "cash",
            "diluted_shares",
            "net_interest_income",
            "credit_loss_provision",
            "deposits",
            "cet1_ratio",
        ),
    },
    "TSM": {
        "template": "semiconductor",
        "allowed_missing": ("gross_profit", "operating_income"),
        "periods": 8,
        "metrics": (
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "operating_cash_flow",
            "capital_expenditure",
            "cash",
            "diluted_shares",
            "inventory",
            "research_and_development",
            "productive_asset_capex",
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--periods", type=int)
    args = parser.parse_args()
    resolver = TickerResolver()
    client = SECClient()
    output: list[dict] = []
    for ticker, settings in MATRIX.items():
        identity = resolver.resolve(ticker)
        if identity is None:
            raise RuntimeError(f"ticker not resolved: {ticker}")
        facts = merge_company_facts(
            client.get_company_facts(identity.cik),
            *(client.get_company_facts(cik) for cik in identity.historical_ciks),
        )
        snapshot = FinancialSnapshotBuilder(settings["template"]).build(
            ticker=ticker,
            cik=identity.cik,
            company_name=identity.name,
            facts=facts,
        )
        report = reconcile_financial_snapshot(
            snapshot,
            facts,
            metrics=settings.get("metrics", CORE_METRICS),
            expected_periods=args.periods or settings["periods"],
            allowed_missing=settings["allowed_missing"],
        )
        output.append(
            {
                "ticker": ticker,
                "template": settings["template"],
                "passed": report.passed,
                "metrics": [asdict(item) for item in report.metrics],
            }
        )
    print(json.dumps(output, indent=2))
    return 0 if all(item["passed"] for item in output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
