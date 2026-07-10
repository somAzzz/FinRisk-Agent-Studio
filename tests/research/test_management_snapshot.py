from __future__ import annotations

import pytest

from src.research.management_snapshot import (
    build_management_snapshot,
    compare_management_snapshots,
)
from src.schemas.transcripts import Transcript, TranscriptTurn


def _transcript(
    *,
    year: int,
    quarter: int,
    prepared: str,
    qa: str,
) -> Transcript:
    return Transcript(
        ticker="ACME",
        year=year,
        quarter=quarter,
        provider="fixture",
        transcript_id=f"ACME-{year}Q{quarter}",
        url=f"https://example.com/{year}q{quarter}",
        turns=[
            TranscriptTurn(
                speaker="CEO",
                role="ceo",
                text=prepared,
                section="prepared_remarks",
                turn_index=0,
            ),
            TranscriptTurn(
                speaker="CFO",
                role="cfo",
                text=qa,
                section="qa",
                turn_index=1,
            ),
        ],
    )


def test_snapshot_preserves_topics_sections_and_evidence() -> None:
    snapshot = build_management_snapshot(
        _transcript(
            year=2026,
            quarter=1,
            prepared="We raised guidance on robust demand and strong growth.",
            qa="Margins remain under pressure and the outlook could be volatile.",
        )
    )

    assert snapshot.guidance_signal == "raised"
    assert snapshot.prepared_remarks_tone == "positive"
    assert snapshot.qa_tone in {"negative", "mixed"}
    assert {item.topic for item in snapshot.topic_signals} >= {
        "demand", "margin", "guidance",
    }
    assert snapshot.evidence_ids == [
        "ACME-2026Q1:turn:0", "ACME-2026Q1:turn:1",
    ]


def test_compare_surfaces_guidance_tone_and_topic_changes() -> None:
    previous = build_management_snapshot(
        _transcript(
            year=2025,
            quarter=4,
            prepared="We lowered guidance as demand was weak.",
            qa="Margins face challenging pressure and uncertainty.",
        )
    )
    current = build_management_snapshot(
        _transcript(
            year=2026,
            quarter=1,
            prepared="We raised guidance as demand is robust and strong.",
            qa="Margins improved with pricing momentum.",
        )
    )

    changes = compare_management_snapshots(previous, current)
    dimensions = {change.dimension for change in changes}
    assert "guidance_signal" in dimensions
    assert "topic:demand" in dimensions
    demand = next(change for change in changes if change.dimension == "topic:demand")
    assert demand.direction == "strengthened"
    assert demand.evidence_ids


def test_compare_rejects_different_companies() -> None:
    snapshot = build_management_snapshot(
        _transcript(
            year=2026,
            quarter=1,
            prepared="Demand is strong.",
            qa="Margins are stable.",
        )
    )
    with pytest.raises(ValueError):
        compare_management_snapshots(
            snapshot,
            snapshot.model_copy(update={"ticker": "OTHER"}),
        )
