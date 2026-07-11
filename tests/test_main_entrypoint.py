from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import main as entrypoint
from src.research.monitor import MonitorScanResponse, TickerScanResult


def test_api_command_starts_canonical_app() -> None:
    with patch("uvicorn.run") as run:
        result = entrypoint.main(["api", "--host", "0.0.0.0", "--port", "9000"])
    assert result == 0
    run.assert_called_once_with(
        "src.api.main:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
    )


def test_workflow_command_forwards_arguments() -> None:
    with patch("src.workflows.finrisk_workflow.main", return_value=0) as run:
        result = entrypoint.main(["workflow", "--ticker", "AAPL", "--analysis-goal", "risks"])
    assert result == 0
    run.assert_called_once_with(["--ticker", "AAPL", "--analysis-goal", "risks"])


def test_monitor_command_runs_one_shot_scan(capsys) -> None:
    response = MonitorScanResponse(
        started_at=datetime(2026, 7, 11, tzinfo=UTC),
        completed_at=datetime(2026, 7, 11, tzinfo=UTC),
        dry_run=True,
        results=[TickerScanResult(ticker="AAPL", status="unchanged")],
    )
    with patch("src.api.research.get_watchlist_monitor") as get_monitor:
        get_monitor.return_value.scan.return_value = response
        result = entrypoint.main(["monitor", "--ticker", "AAPL", "--dry-run"])
    assert result == 0
    request = get_monitor.return_value.scan.call_args.args[0]
    assert request.tickers == ["AAPL"]
    assert request.dry_run is True
    assert '"ticker": "AAPL"' in capsys.readouterr().out


def test_database_migrate_command(tmp_path, capsys) -> None:
    path = tmp_path / "research.sqlite"

    result = entrypoint.main(["database", "migrate", "--path", str(path)])

    assert result == 0
    assert "schema version: 2" in capsys.readouterr().out
