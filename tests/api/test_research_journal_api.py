from __future__ import annotations

from pathlib import Path

import pytest

from src.api.research import (
    get_investment_thesis,
    list_investment_theses,
    list_watchlist,
    review_investment_thesis,
    save_investment_thesis,
    save_watchlist_item,
    set_research_journal_store_for_tests,
)
from src.research.journal import (
    InvestmentThesis,
    ResearchJournalStore,
    ThesisReview,
    WatchlistItem,
)


@pytest.fixture(autouse=True)
def _journal(tmp_path: Path):
    set_research_journal_store_for_tests(
        ResearchJournalStore(tmp_path / "journal.sqlite")
    )
    yield
    set_research_journal_store_for_tests(None)


def _thesis() -> InvestmentThesis:
    return InvestmentThesis(
        thesis_id="thesis-api",
        ticker="ACME",
        statement="Pricing may support margin recovery.",
        time_horizon="12 months",
        status="active",
        disconfirming_conditions=["Operating margin declines for two quarters"],
    )


@pytest.mark.asyncio
async def test_thesis_crud_review_and_watchlist() -> None:
    saved = await save_investment_thesis(_thesis())
    assert (await get_investment_thesis(saved.thesis_id)).ticker == "ACME"
    assert len(await list_investment_theses("ACME", "active")) == 1

    reviewed = await review_investment_thesis(
        saved.thesis_id,
        ThesisReview(outcome="invalidated", notes="Condition was breached."),
    )
    assert reviewed.status == "invalidated"

    item = await save_watchlist_item(
        "ACME",
        WatchlistItem(ticker="ACME", thesis_ids=[saved.thesis_id]),
    )
    assert item.thesis_ids == [saved.thesis_id]
    assert [entry.ticker for entry in await list_watchlist()] == ["ACME"]
