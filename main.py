"""Convenience CLI for the FinRisk API and workflow runner."""

from __future__ import annotations

import argparse
import json
from datetime import date


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fintext-llm",
        description="Run the FinRisk Agent Studio API or a company workflow.",
    )
    commands = parser.add_subparsers(dest="command")
    api = commands.add_parser("api", help="Start the FastAPI service")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    commands.add_parser(
        "workflow",
        help="Run the FinRisk workflow; remaining options go to the workflow CLI",
        add_help=False,
    )
    monitor = commands.add_parser(
        "monitor",
        help="Run one incremental Watchlist research scan",
    )
    monitor.add_argument("--ticker", action="append", dest="tickers")
    monitor.add_argument("--as-of", type=date.fromisoformat)
    monitor.add_argument("--year", type=int)
    monitor.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    monitor.add_argument(
        "--minimum-materiality",
        choices=("low", "medium", "high"),
        default="medium",
    )
    monitor.add_argument("--max-workers", type=int, default=2)
    monitor.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, remaining = parser.parse_known_args(argv)
    if args.command == "api":
        import uvicorn

        uvicorn.run(
            "src.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    if args.command == "workflow":
        from src.workflows.finrisk_workflow import main as workflow_main

        return workflow_main(remaining)
    if args.command == "monitor":
        from src.api.research import get_watchlist_monitor
        from src.research.monitor import MonitorScanRequest

        response = get_watchlist_monitor().scan(
            MonitorScanRequest(
                tickers=args.tickers,
                as_of=args.as_of,
                minimum_materiality=args.minimum_materiality,
                max_workers=args.max_workers,
                dry_run=args.dry_run,
                year=args.year,
                quarter=args.quarter,
            )
        )
        print(json.dumps(response.model_dump(mode="json"), indent=2))
        return 1 if any(item.status == "failed" for item in response.results) else 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
