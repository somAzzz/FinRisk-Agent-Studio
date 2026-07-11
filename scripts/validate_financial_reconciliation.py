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
    "AAPL": {"template": "general", "allowed_missing": ()},
    "NVDA": {"template": "semiconductor", "allowed_missing": ()},
    "XOM": {
        "template": "energy",
        "allowed_missing": ("gross_profit", "operating_income"),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--periods", type=int, default=12)
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
            metrics=CORE_METRICS,
            expected_periods=args.periods,
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
