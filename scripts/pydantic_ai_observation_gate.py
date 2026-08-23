#!/usr/bin/env python3
"""Evaluate persisted primary runs before changing the runtime default."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.migration_observation import (  # noqa: E402
    evaluate_primary_observation,
)
from src.api.store_factory import (  # noqa: E402
    get_agent_run_store,
    reset_run_store_for_tests,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate primary duration, failures and fallback-zero gates."
    )
    parser.add_argument(
        "--db",
        default=os.environ.get(
            "RUN_STORE_DB", ".cache/finrisk_agent_studio/runs.sqlite3"
        ),
    )
    parser.add_argument("--required-runs", type=int, default=20)
    parser.add_argument("--required-hours", type=float, default=168.0)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--output", help="Optional JSON report path.")
    return parser.parse_args()


async def _load_states(db_path: str, limit: int):
    os.environ["RUN_STORE_BACKEND"] = "sqlite"
    os.environ["RUN_STORE_DB"] = db_path
    reset_run_store_for_tests()
    return await get_agent_run_store().list_recent(limit)


def main() -> int:
    args = _parse_args()
    states = asyncio.run(_load_states(args.db, args.limit))
    report = evaluate_primary_observation(
        states,
        required_runs=args.required_runs,
        required_hours=args.required_hours,
    )
    rendered = report.model_dump_json(indent=2)
    print(rendered)
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.ready else 2


if __name__ == "__main__":
    sys.exit(main())
