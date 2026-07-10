from __future__ import annotations

from datetime import UTC, date, datetime

from src.research.management_snapshot import ManagementPeriodSnapshot
from src.research.models import FinancialMetricPoint, FinancialSnapshot
from src.research.orchestrator import (
    CompanyResearchOrchestrator,
    ResearchRunRequest,
)
from src.research.snapshot_store import ResearchSnapshotStore


def _financials(ticker: str, as_of: date | None) -> FinancialSnapshot:
    selected = as_of or date(2026, 4, 30)
    return FinancialSnapshot(
        ticker=ticker,
        cik="0000000001",
        as_of=datetime(selected.year, selected.month, selected.day, tzinfo=UTC),
        metrics=[
            FinancialMetricPoint(
                metric="revenue",
                value=100.0,
                unit="USD",
                period_end=date(2026, 3, 31),
                period_kind="quarter",
                source_concept="Revenue",
                accession_number="0001-26-000001",
                filed_at=date(2026, 4, 20),
            )
        ],
    )


def _management(ticker: str, year: int, quarter: int) -> ManagementPeriodSnapshot:
    return ManagementPeriodSnapshot(
        ticker=ticker,
        year=year,
        quarter=quarter,
        transcript_id=f"{ticker}-{year}Q{quarter}",
        provider="fixture",
        overall_tone="positive",
        uncertainty=0.1,
        defensiveness=0.1,
        guidance_signal="maintained",
    )


def test_orchestrator_builds_auditable_idempotent_snapshot(tmp_path) -> None:
    store = ResearchSnapshotStore(tmp_path / "snapshots.sqlite")
    orchestrator = CompanyResearchOrchestrator(
        store=store,
        financial_loader=_financials,
        management_loader=_management,
    )
    request = ResearchRunRequest(
        ticker="acme",
        as_of=date(2026, 4, 30),
        year=2026,
        quarter=1,
        include_risks=False,
    )

    first = orchestrator.run(request)
    second = orchestrator.run(request)

    assert first.snapshot is not None
    assert second.snapshot is not None
    assert second.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert first.manifest.state == "completed"
    assert {source.source_type for source in first.snapshot.sources} == {
        "sec_filing",
        "transcript",
    }
    assert len(store.list_snapshots("ACME")) == 1
    assert store.get_run(first.manifest.run_id) == first.manifest


def test_orchestrator_persists_partial_snapshot_on_provider_failure(tmp_path) -> None:
    store = ResearchSnapshotStore(tmp_path / "snapshots.sqlite")

    def unavailable(_ticker: str, _as_of: date | None) -> FinancialSnapshot:
        raise TimeoutError("secret provider response")

    orchestrator = CompanyResearchOrchestrator(
        store=store,
        financial_loader=unavailable,
    )

    response = orchestrator.run(
        ResearchRunRequest(
            ticker="ACME",
            as_of=date(2026, 4, 30),
            include_management=False,
            include_risks=False,
        )
    )

    assert response.manifest.state == "failed"
    assert response.snapshot is not None
    assert response.snapshot.financials is None
    assert response.snapshot.components[0].reason == ("financial data unavailable: TimeoutError")
    assert "secret provider response" not in response.snapshot.model_dump_json()
