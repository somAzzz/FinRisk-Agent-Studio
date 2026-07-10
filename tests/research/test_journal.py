from __future__ import annotations

from pathlib import Path

from src.research.journal import (
    Catalyst,
    InvestmentThesis,
    ResearchJournalStore,
    ThesisReview,
    WatchlistItem,
)


def _thesis() -> InvestmentThesis:
    return InvestmentThesis(
        thesis_id="thesis-1",
        ticker="acme",
        statement="Margin recovery depends on mix and pricing.",
        time_horizon="12 months",
        status="active",
        key_drivers=["services mix", "pricing"],
        risks=["input cost inflation"],
        disconfirming_conditions=["Gross margin remains below 30% for two quarters"],
        monitoring_metrics=["gross_margin", "revenue"],
        evidence_ids=["filing-1"],
    )


def test_persists_filters_and_reviews_theses(tmp_path: Path) -> None:
    store = ResearchJournalStore(tmp_path / "journal.sqlite")
    saved = store.save_thesis(_thesis())

    assert saved.ticker == "ACME"
    assert store.get_thesis("thesis-1") is not None
    assert len(store.list_theses(ticker="ACME", status="active")) == 1

    reviewed = store.add_review(
        "thesis-1",
        ThesisReview(
            outcome="invalidated",
            notes="Two reported quarters breached the falsification condition.",
            evidence_ids=["quarter-1", "quarter-2"],
        ),
    )
    assert reviewed.status == "invalidated"
    assert reviewed.reviews[0].evidence_ids == ["quarter-1", "quarter-2"]
    assert store.list_theses(status="active") == []


def test_watchlist_upsert_and_active_filter(tmp_path: Path) -> None:
    store = ResearchJournalStore(tmp_path / "journal.sqlite")
    store.save_watchlist_item(
        WatchlistItem(
            ticker="ACME",
            thesis_ids=["thesis-1"],
            monitoring_questions=["Has gross margin recovered?"],
        )
    )
    store.save_watchlist_item(WatchlistItem(ticker="OLD", active=False))

    assert [item.ticker for item in store.list_watchlist()] == ["ACME"]
    assert {item.ticker for item in store.list_watchlist(active_only=False)} == {
        "ACME", "OLD",
    }


def test_due_reminders_cover_reviews_and_catalysts(tmp_path: Path) -> None:
    from datetime import date

    store = ResearchJournalStore(tmp_path / "journal.sqlite")
    store.save_thesis(
        _thesis().model_copy(
            update={
                "catalysts": [
                    Catalyst(
                        catalyst_id="cat-earnings",
                        title="Quarterly earnings",
                        expected_date=date(2026, 7, 20),
                    )
                ]
            }
        )
    )
    store.save_watchlist_item(
        WatchlistItem(
            ticker="ACME",
            thesis_ids=["thesis-1"],
            next_review_date=date(2026, 7, 5),
        )
    )

    reminders = store.list_due_reminders(
        as_of=date(2026, 7, 11),
        horizon_days=14,
    )
    assert [item.reminder_type for item in reminders] == [
        "thesis_review", "catalyst",
    ]
    assert reminders[0].overdue is True
    assert reminders[1].overdue is False
