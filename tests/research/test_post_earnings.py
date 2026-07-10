from __future__ import annotations

from datetime import UTC, datetime

from src.research.change_detection import ResearchChange
from src.research.journal import InvestmentThesis, ResearchJournalStore
from src.research.models import CompanyResearchSnapshot
from src.research.post_earnings import (
    ConfirmPostEarningsReviewRequest,
    PostEarningsReviewStore,
    build_post_earnings_review_draft,
)


def _snapshot(snapshot_id: str, year: int) -> CompanyResearchSnapshot:
    return CompanyResearchSnapshot(
        snapshot_id=snapshot_id,
        ticker="ACME",
        period=f"{year}Q1",
        as_of=datetime(year, 4, 30, tzinfo=UTC),
        source_fingerprint=f"fingerprint-{year}",
    )


def test_post_earnings_confirmation_preserves_locked_thesis_and_is_idempotent(
    tmp_path,
) -> None:
    database = tmp_path / "research.sqlite"
    journal = ResearchJournalStore(database)
    review_store = PostEarningsReviewStore(database)
    thesis = journal.save_thesis(
        InvestmentThesis(
            thesis_id="thesis-one",
            ticker="ACME",
            statement="Revenue growth remains durable",
            time_horizon="12 months",
            status="active",
            disconfirming_conditions=["revenue growth weakens"],
        )
    )
    change = ResearchChange(
        change_id="change-one",
        ticker="ACME",
        category="financial",
        key="revenue growth",
        status="weakened",
        materiality="high",
        before={"value": 120},
        after={"value": 90},
        before_evidence_ids=["old-filing"],
        after_evidence_ids=["new-filing"],
        detection_method="test",
        explanation="revenue growth weakens",
        confidence=1.0,
    )
    draft = build_post_earnings_review_draft(
        thesis=thesis,
        previous=_snapshot("old", 2025),
        current=_snapshot("new", 2026),
        changes=[change],
        locked_assumptions={"base_growth": 0.1},
    )
    saved = review_store.save(draft)

    assert saved.suggested_outcome == "invalidated"
    assert saved.locked_thesis_statement == thesis.statement
    assert saved.locked_assumptions == {"base_growth": 0.1}

    confirmed = review_store.confirm(
        saved.draft_id,
        ConfirmPostEarningsReviewRequest(
            outcome="mixed",
            notes="Demand held up better than the first signal implied.",
        ),
        journal,
    )
    repeated = review_store.confirm(
        saved.draft_id,
        ConfirmPostEarningsReviewRequest(
            outcome="invalidated",
            notes="Must not add a second review.",
        ),
        journal,
    )

    updated_thesis = journal.get_thesis(thesis.thesis_id)
    assert updated_thesis is not None
    assert updated_thesis.statement == thesis.statement
    assert updated_thesis.disconfirming_conditions == thesis.disconfirming_conditions
    assert len(updated_thesis.reviews) == 1
    assert updated_thesis.reviews[0].outcome == "mixed"
    assert repeated.confirmed_review_id == confirmed.confirmed_review_id


def test_post_earnings_draft_rejects_reverse_periods() -> None:
    thesis = InvestmentThesis(
        ticker="ACME",
        statement="Test",
        time_horizon="one year",
        disconfirming_conditions=["condition"],
    )
    try:
        build_post_earnings_review_draft(
            thesis=thesis,
            previous=_snapshot("new", 2026),
            current=_snapshot("old", 2025),
            changes=[],
        )
    except ValueError as exc:
        assert "newer" in str(exc)
    else:
        raise AssertionError("reverse period comparison should fail")
