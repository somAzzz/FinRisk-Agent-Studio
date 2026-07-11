from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.research.change_detection import detect_research_changes
from src.research.management_snapshot import ManagementPeriodSnapshot
from src.research.models import (
    CompanyResearchSnapshot,
    FinancialMetricPoint,
    FinancialSnapshot,
    RiskObservation,
    SnapshotComponentResult,
    SourceManifestEntry,
)


def _snapshot(
    *,
    snapshot_id: str,
    as_of: datetime,
    revenue: float,
    guidance: str,
    risks: list[RiskObservation] | None = None,
) -> CompanyResearchSnapshot:
    period_end = date(as_of.year, 3, 31)
    accession = f"filing-{snapshot_id}"
    return CompanyResearchSnapshot(
        snapshot_id=snapshot_id,
        ticker="ACME",
        period=f"{as_of.year}Q1",
        as_of=as_of,
        source_fingerprint=f"fingerprint-{snapshot_id}",
        financials=FinancialSnapshot(
            ticker="ACME",
            cik="1",
            as_of=as_of,
            metrics=[
                FinancialMetricPoint(
                    metric="revenue",
                    value=revenue,
                    unit="USD",
                    period_end=period_end,
                    period_kind="quarter",
                    source_concept="Revenue",
                    accession_number=accession,
                    filed_at=as_of.date(),
                )
            ],
        ),
        management=ManagementPeriodSnapshot(
            ticker="ACME",
            year=as_of.year,
            quarter=1,
            transcript_id=f"transcript-{snapshot_id}",
            provider="fixture",
            overall_tone="neutral",
            uncertainty=0.2,
            defensiveness=0.2,
            guidance_signal=guidance,
            evidence_ids=[f"evidence-{snapshot_id}"],
        ),
        risks=risks or [],
        sources=[
            SourceManifestEntry(
                source_id=accession,
                source_type="sec_filing",
                provider="SEC",
                as_of=as_of,
            )
        ],
    )


def test_detects_evidence_linked_financial_guidance_and_risk_changes() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2025, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        revenue=120,
        guidance="raised",
        risks=[
            RiskObservation(
                risk_id="supply",
                title="Supplier concentration",
                status="new",
                evidence_ids=["risk-evidence"],
            )
        ],
    )

    first = detect_research_changes(previous, current)
    second = detect_research_changes(previous, current)

    assert [item.change_id for item in first.changes] == [item.change_id for item in second.changes]
    financial = next(item for item in first.changes if item.category == "financial")
    assert financial.materiality == "high"
    assert financial.before_evidence_ids == ["filing-old"]
    assert financial.after_evidence_ids == ["filing-new"]
    guidance = next(item for item in first.changes if item.category == "guidance")
    assert guidance.before == "maintained"
    assert guidance.after == "raised"
    assert any(item.category == "risk" and item.status == "new" for item in first.changes)


def test_rejects_reverse_or_cross_company_comparison() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2025, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    with pytest.raises(ValueError, match="newer"):
        detect_research_changes(current, previous)
    with pytest.raises(ValueError, match="same ticker"):
        detect_research_changes(
            previous,
            current.model_copy(update={"ticker": "OTHER"}),
        )


def test_unavailable_risk_component_does_not_create_false_resolution() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2025, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
        risks=[
            RiskObservation(
                risk_id="supply",
                title="Supplier concentration",
                evidence_ids=["old-risk-evidence"],
            )
        ],
    ).model_copy(
        update={
            "components": [
                SnapshotComponentResult(component="risks", state="complete")
            ]
        }
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    ).model_copy(
        update={
            "components": [
                SnapshotComponentResult(
                    component="risks",
                    state="unavailable",
                    reason="adapter unavailable",
                )
            ]
        }
    )

    result = detect_research_changes(previous, current)

    assert not any(
        change.category == "risk" and change.status == "resolved"
        for change in result.changes
    )
    assert result.warnings == ["component_not_comparable:risks:unavailable"]


def test_propagates_snapshot_correlation_to_change_set() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2025, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        revenue=120,
        guidance="maintained",
    ).model_copy(update={"correlation_id": "workflow-123"})

    result = detect_research_changes(previous, current)

    assert result.correlation_id == "workflow-123"


def test_detects_source_staleness_threshold_crossing() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2026, 1, 20, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 3, 20, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    ).model_copy(update={"sources": previous.sources})

    result = detect_research_changes(
        previous,
        current,
        source_stale_after_days=45,
    )

    stale = next(change for change in result.changes if "source_stale" in change.key)
    assert stale.status == "weakened"
    assert stale.after["threshold_days"] == 45


def test_detects_conflicting_normalized_source_values() -> None:
    previous = _snapshot(
        snapshot_id="old",
        as_of=datetime(2025, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    )
    current = _snapshot(
        snapshot_id="new",
        as_of=datetime(2026, 4, 30, tzinfo=UTC),
        revenue=100,
        guidance="maintained",
    ).model_copy(
        update={
            "sources": [
                SourceManifestEntry(
                    source_id="provider-a",
                    source_type="other",
                    provider="A",
                    as_of=datetime(2026, 4, 30, tzinfo=UTC),
                    metadata={"fact_key": "guidance:revenue", "value": 100},
                ),
                SourceManifestEntry(
                    source_id="provider-b",
                    source_type="other",
                    provider="B",
                    as_of=datetime(2026, 4, 30, tzinfo=UTC),
                    metadata={"fact_key": "guidance:revenue", "value": 120},
                ),
            ]
        }
    )

    result = detect_research_changes(previous, current)

    conflict = next(
        change for change in result.changes if "source_conflict" in change.key
    )
    assert conflict.status == "new"
    assert conflict.after_evidence_ids == ["provider-a", "provider-b"]
