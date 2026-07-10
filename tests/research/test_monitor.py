from __future__ import annotations

from datetime import UTC, date, datetime

from src.research.alert_store import AlertActionRequest, ResearchAlertStore
from src.research.change_store import ResearchChangeStore
from src.research.journal import ResearchJournalStore, WatchlistItem
from src.research.models import FinancialMetricPoint, FinancialSnapshot
from src.research.monitor import MonitorScanRequest, WatchlistMonitor
from src.research.orchestrator import CompanyResearchOrchestrator
from src.research.snapshot_store import ResearchSnapshotStore


def _financials(ticker: str, as_of: date | None) -> FinancialSnapshot:
    if ticker == "FAIL":
        raise TimeoutError("provider secret")
    selected = as_of or date(2026, 4, 30)
    value = 100 if selected.year == 2025 else 120
    return FinancialSnapshot(
        ticker=ticker,
        cik="1",
        as_of=datetime(selected.year, selected.month, selected.day, tzinfo=UTC),
        metrics=[
            FinancialMetricPoint(
                metric="revenue",
                value=value,
                unit="USD",
                period_end=date(selected.year, 3, 31),
                period_kind="quarter",
                source_concept="Revenue",
                accession_number=f"filing-{ticker}-{selected.year}",
                filed_at=date(selected.year, 4, 20),
            )
        ],
    )


def _monitor(tmp_path) -> tuple[WatchlistMonitor, ResearchAlertStore, ResearchSnapshotStore]:
    database = tmp_path / "research.sqlite"
    snapshots = ResearchSnapshotStore(database)
    alerts = ResearchAlertStore(database)
    journal = ResearchJournalStore(database)
    journal.save_watchlist_item(WatchlistItem(ticker="ACME"))
    orchestrator = CompanyResearchOrchestrator(
        store=snapshots,
        financial_loader=_financials,
    )
    return (
        WatchlistMonitor(
            orchestrator=orchestrator,
            snapshot_store=snapshots,
            change_store=ResearchChangeStore(database),
            alert_store=alerts,
            journal_store=journal,
        ),
        alerts,
        snapshots,
    )


def test_monitor_only_alerts_once_for_new_material_change(tmp_path) -> None:
    monitor, alerts, _snapshots = _monitor(tmp_path)

    first = monitor.scan(MonitorScanRequest(as_of=date(2025, 4, 30)))
    second = monitor.scan(MonitorScanRequest(as_of=date(2026, 4, 30)))
    third = monitor.scan(MonitorScanRequest(as_of=date(2026, 4, 30)))

    assert first.results[0].new_alerts == []
    assert len(second.results[0].new_alerts) == 1
    assert second.results[0].new_alerts[0].materiality == "high"
    assert third.results[0].status == "unchanged"
    assert len(alerts.list_alerts(ticker="ACME")) == 1

    alert = alerts.list_alerts()[0]
    alerts.act(alert.alert_id, AlertActionRequest(action="ignore"))
    assert alerts.list_alerts(status="ignored")[0].alert_id == alert.alert_id


def test_monitor_dry_run_does_not_persist_snapshot_alert_or_cursor(tmp_path) -> None:
    monitor, alerts, snapshots = _monitor(tmp_path)
    monitor.scan(MonitorScanRequest(as_of=date(2025, 4, 30)))

    response = monitor.scan(MonitorScanRequest(as_of=date(2026, 4, 30), dry_run=True))

    assert len(response.results[0].new_alerts) == 1
    assert len(snapshots.list_snapshots("ACME")) == 1
    assert alerts.list_alerts() == []
    assert alerts.get_cursor("ACME").snapshot_id == snapshots.list_snapshots("ACME")[0].snapshot_id


def test_monitor_isolates_company_failures(tmp_path) -> None:
    monitor, _alerts, _snapshots = _monitor(tmp_path)

    response = monitor.scan(
        MonitorScanRequest(
            tickers=["ACME", "FAIL"],
            as_of=date(2026, 4, 30),
            max_workers=2,
        )
    )

    results = {item.ticker: item for item in response.results}
    assert results["ACME"].status == "partial"
    assert results["FAIL"].status == "failed"
    assert results["FAIL"].error is None
    failed_snapshot = _snapshots.get_snapshot(results["FAIL"].snapshot_id)
    assert failed_snapshot is not None
    assert "provider secret" not in failed_snapshot.model_dump_json()


def test_default_scan_keeps_cursor_on_persisted_snapshot_when_sources_unchanged(
    tmp_path,
) -> None:
    monitor, alerts, snapshots = _monitor(tmp_path)

    first = monitor.scan(MonitorScanRequest())
    second = monitor.scan(MonitorScanRequest())

    assert second.results[0].status == "unchanged"
    assert second.results[0].snapshot_id == first.results[0].snapshot_id
    assert len(snapshots.list_snapshots("ACME")) == 1
    cursor = alerts.get_cursor("ACME")
    assert cursor is not None
    assert cursor.snapshot_id == first.results[0].snapshot_id
