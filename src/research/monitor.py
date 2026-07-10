"""One-shot Watchlist scanner with failure isolation and alert deduplication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.alert_store import MonitorCursor, ResearchAlert, ResearchAlertStore
from src.research.change_detection import Materiality, detect_research_changes
from src.research.change_store import ResearchChangeStore
from src.research.journal import ResearchJournalStore, WatchlistItem
from src.research.orchestrator import CompanyResearchOrchestrator, ResearchRunRequest
from src.research.snapshot_store import ResearchSnapshotStore


class MonitorScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: list[str] | None = None
    as_of: date | None = None
    minimum_materiality: Literal["low", "medium", "high"] = "medium"
    max_workers: int = Field(default=2, ge=1, le=8)
    dry_run: bool = False
    year: int | None = Field(default=None, ge=1990, le=2100)
    quarter: int | None = Field(default=None, ge=1, le=4)

    def model_post_init(self, _context: object) -> None:
        if (self.year is None) != (self.quarter is None):
            raise ValueError("year and quarter must be provided together")


class TickerScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    status: Literal["completed", "unchanged", "partial", "failed"]
    snapshot_id: str | None = None
    new_alerts: list[ResearchAlert] = Field(default_factory=list)
    change_count: int = 0
    error: str | None = None


class MonitorScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    completed_at: datetime
    dry_run: bool
    results: list[TickerScanResult]


class WatchlistMonitor:
    def __init__(
        self,
        *,
        orchestrator: CompanyResearchOrchestrator,
        snapshot_store: ResearchSnapshotStore,
        change_store: ResearchChangeStore,
        alert_store: ResearchAlertStore,
        journal_store: ResearchJournalStore,
    ) -> None:
        self.orchestrator = orchestrator
        self.snapshot_store = snapshot_store
        self.change_store = change_store
        self.alert_store = alert_store
        self.journal_store = journal_store

    def scan(self, request: MonitorScanRequest) -> MonitorScanResponse:
        started = datetime.now(UTC)
        items = self._items(request.tickers)
        results: list[TickerScanResult] = []
        with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
            futures = {executor.submit(self._scan_ticker, item, request): item.ticker for item in items}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # isolate each company and redact details
                    results.append(
                        TickerScanResult(
                            ticker=ticker,
                            status="failed",
                            error=f"scan failed: {type(exc).__name__}",
                        )
                    )
        return MonitorScanResponse(
            started_at=started,
            completed_at=datetime.now(UTC),
            dry_run=request.dry_run,
            results=sorted(results, key=lambda item: item.ticker),
        )

    def _items(self, tickers: list[str] | None) -> list[WatchlistItem]:
        watchlist = self.journal_store.list_watchlist()
        if tickers is None:
            return watchlist
        requested = {ticker.upper().strip() for ticker in tickers}
        indexed = {item.ticker: item for item in watchlist}
        return [indexed.get(ticker, WatchlistItem(ticker=ticker)) for ticker in sorted(requested)]

    def _scan_ticker(
        self,
        item: WatchlistItem,
        request: MonitorScanRequest,
    ) -> TickerScanResult:
        previous_snapshots = self.snapshot_store.list_snapshots(item.ticker, limit=1)
        previous = previous_snapshots[0] if previous_snapshots else None
        run = self.orchestrator.run(
            ResearchRunRequest(
                ticker=item.ticker,
                as_of=request.as_of,
                year=request.year,
                quarter=request.quarter,
                include_management=request.year is not None,
                include_risks=True,
            ),
            persist=False,
        )
        current = run.snapshot
        if current is None:
            return TickerScanResult(
                ticker=item.ticker,
                status="failed",
                error="snapshot was not created",
            )
        if previous and previous.source_fingerprint == current.source_fingerprint:
            if not request.dry_run:
                self._save_cursor(previous)
            return TickerScanResult(
                ticker=item.ticker,
                status="unchanged",
                snapshot_id=previous.snapshot_id,
            )
        if not request.dry_run:
            current = self.snapshot_store.save_snapshot(current)
            self.snapshot_store.save_run(run.manifest)
        changes = []
        alerts: list[ResearchAlert] = []
        if previous and previous.as_of < current.as_of:
            change_set = detect_research_changes(previous, current)
            changes = change_set.changes
            if not request.dry_run:
                self.change_store.save_change_set(change_set)
            for change in changes:
                if not _meets_threshold(change.materiality, request.minimum_materiality):
                    continue
                if request.dry_run:
                    alert = ResearchAlert(
                        alert_id=f"alert-{change.change_id.removeprefix('change-')}",
                        change_id=change.change_id,
                        ticker=change.ticker,
                        materiality=change.materiality,
                        title=f"{change.category}: {change.key}",
                        explanation=change.explanation,
                        snapshot_id=current.snapshot_id,
                    )
                    alerts.append(alert)
                else:
                    alert, created = self.alert_store.create_for_change(
                        change,
                        snapshot_id=current.snapshot_id,
                    )
                    if created:
                        alerts.append(alert)
        if not request.dry_run:
            self._save_cursor(current)
        status = run.manifest.state
        return TickerScanResult(
            ticker=item.ticker,
            status=status,
            snapshot_id=current.snapshot_id,
            new_alerts=alerts,
            change_count=len(changes),
        )

    def _save_cursor(self, snapshot) -> None:
        self.alert_store.save_cursor(
            MonitorCursor(
                ticker=snapshot.ticker,
                snapshot_id=snapshot.snapshot_id,
                source_fingerprint=snapshot.source_fingerprint,
                last_success_at=datetime.now(UTC),
            )
        )


def _meets_threshold(
    materiality: Materiality,
    minimum: Literal["low", "medium", "high"],
) -> bool:
    if materiality == "unknown":
        return True
    rank = {"low": 0, "medium": 1, "high": 2}
    return rank[materiality] >= rank[minimum]


__all__ = [
    "MonitorScanRequest",
    "MonitorScanResponse",
    "TickerScanResult",
    "WatchlistMonitor",
]
