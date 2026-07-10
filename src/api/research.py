"""Point-in-time financial research endpoints."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from src.research import FinancialSnapshot, FinancialSnapshotBuilder
from src.research.financial_snapshot import merge_company_facts
from src.research.journal import (
    InvestmentThesis,
    ResearchJournalStore,
    ResearchReminder,
    ThesisReview,
    ThesisStatus,
    WatchlistItem,
)
from src.research.management_snapshot import (
    ManagementComparisonResponse,
    build_management_snapshot,
    compare_management_snapshots,
)
from src.research.valuation import (
    ScenarioValuationRequest,
    ScenarioValuationResponse,
    calculate_scenario_valuation,
)

router = APIRouter(prefix="/research")


class FinancialResearchService:
    """Resolve a company and build a normalized SEC financial snapshot."""

    def __init__(
        self,
        *,
        ticker_resolver: Any | None = None,
        company_facts_fetcher: Any | None = None,
    ) -> None:
        self._ticker_resolver = ticker_resolver
        self._company_facts_fetcher = company_facts_fetcher

    def build_snapshot(
        self,
        ticker: str,
        as_of: date | None = None,
    ) -> FinancialSnapshot:
        resolver = self._ticker_resolver or self._default_resolver()
        ident = resolver.resolve(ticker)
        if ident is None:
            raise LookupError(f"ticker not resolved: {ticker.upper()}")
        fetcher = self._company_facts_fetcher or self._default_facts_fetcher()
        facts = merge_company_facts(
            fetcher(ident.cik),
            *(fetcher(cik) for cik in getattr(ident, "historical_ciks", [])),
        )
        return FinancialSnapshotBuilder().build(
            ticker=ident.ticker,
            cik=ident.cik,
            company_name=getattr(ident, "name", None),
            facts=facts,
            as_of=as_of,
        )

    @staticmethod
    def _default_resolver() -> Any:
        from src.data.ticker_resolver import TickerResolver

        return TickerResolver()

    @staticmethod
    def _default_facts_fetcher() -> Any:
        from src.data.sec_client import SECClient

        return SECClient().get_company_facts


class ManagementResearchService:
    def __init__(self, transcript_provider: Any | None = None) -> None:
        self._transcript_provider = transcript_provider

    def compare(
        self,
        *,
        ticker: str,
        year: int,
        quarter: int,
        compare_year: int | None = None,
        compare_quarter: int | None = None,
    ) -> ManagementComparisonResponse:
        provider = self._transcript_provider or self._default_provider()
        current = build_management_snapshot(
            provider.get_transcript(ticker.upper(), year, quarter)
        )
        previous = None
        changes = []
        if compare_year is not None and compare_quarter is not None:
            previous = build_management_snapshot(
                provider.get_transcript(
                    ticker.upper(),
                    compare_year,
                    compare_quarter,
                )
            )
            changes = compare_management_snapshots(previous, current)
        return ManagementComparisonResponse(
            current=current,
            previous=previous,
            changes=changes,
        )

    @staticmethod
    def _default_provider() -> Any:
        from src.data.providers.defeatbeta import DefeatBetaProvider

        return DefeatBetaProvider()


_service = FinancialResearchService()
_management_service = ManagementResearchService()
_journal_store: ResearchJournalStore | None = None


def set_financial_research_service_for_tests(
    service: FinancialResearchService,
) -> None:
    global _service
    _service = service


def set_management_research_service_for_tests(
    service: ManagementResearchService,
) -> None:
    global _management_service
    _management_service = service


def get_research_journal_store() -> ResearchJournalStore:
    global _journal_store
    if _journal_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_JOURNAL_PATH",
                ".cache/research_journal.sqlite",
            )
        )
        _journal_store = ResearchJournalStore(path)
    return _journal_store


def set_research_journal_store_for_tests(store: ResearchJournalStore | None) -> None:
    global _journal_store
    _journal_store = store


@router.get(
    "/financials/{ticker}",
    response_model=FinancialSnapshot,
)
async def get_financial_snapshot(
    ticker: str,
    as_of: Annotated[date | None, Query()] = None,
) -> FinancialSnapshot:
    """Return normalized SEC facts known on or before ``as_of``."""
    try:
        return await asyncio.to_thread(_service.build_snapshot, ticker, as_of)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"financial data unavailable: {type(exc).__name__}",
        ) from exc


@router.post(
    "/valuation/scenarios",
    response_model=ScenarioValuationResponse,
)
async def calculate_valuation_scenarios(
    request: ScenarioValuationRequest,
) -> ScenarioValuationResponse:
    """Calculate transparent user-supplied valuation scenarios."""
    return calculate_scenario_valuation(request)


@router.get(
    "/management/{ticker}",
    response_model=ManagementComparisonResponse,
)
async def get_management_comparison(
    ticker: str,
    year: Annotated[int, Query(ge=1990, le=2100)],
    quarter: Annotated[int, Query(ge=1, le=4)],
    compare_year: Annotated[int | None, Query(ge=1990, le=2100)] = None,
    compare_quarter: Annotated[int | None, Query(ge=1, le=4)] = None,
) -> ManagementComparisonResponse:
    if (compare_year is None) != (compare_quarter is None):
        raise HTTPException(
            status_code=422,
            detail="compare_year and compare_quarter must be provided together",
        )
    try:
        return await asyncio.to_thread(
            _management_service.compare,
            ticker=ticker,
            year=year,
            quarter=quarter,
            compare_year=compare_year,
            compare_quarter=compare_quarter,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"transcript comparison unavailable: {type(exc).__name__}",
        ) from exc


@router.post(
    "/theses",
    response_model=InvestmentThesis,
    status_code=status.HTTP_201_CREATED,
)
async def save_investment_thesis(
    thesis: InvestmentThesis,
) -> InvestmentThesis:
    return await asyncio.to_thread(get_research_journal_store().save_thesis, thesis)


@router.get("/theses", response_model=list[InvestmentThesis])
async def list_investment_theses(
    ticker: str | None = None,
    thesis_status: Annotated[
        ThesisStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[InvestmentThesis]:
    return await asyncio.to_thread(
        get_research_journal_store().list_theses,
        ticker=ticker,
        status=thesis_status,
    )


@router.get("/theses/{thesis_id}", response_model=InvestmentThesis)
async def get_investment_thesis(thesis_id: str) -> InvestmentThesis:
    thesis = await asyncio.to_thread(
        get_research_journal_store().get_thesis,
        thesis_id,
    )
    if thesis is None:
        raise HTTPException(status_code=404, detail="thesis not found")
    return thesis


@router.post("/theses/{thesis_id}/reviews", response_model=InvestmentThesis)
async def review_investment_thesis(
    thesis_id: str,
    review: ThesisReview,
) -> InvestmentThesis:
    try:
        return await asyncio.to_thread(
            get_research_journal_store().add_review,
            thesis_id,
            review,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="thesis not found") from exc


@router.put("/watchlist/{ticker}", response_model=WatchlistItem)
async def save_watchlist_item(
    ticker: str,
    item: WatchlistItem,
) -> WatchlistItem:
    if ticker.upper() != item.ticker:
        raise HTTPException(status_code=422, detail="path ticker does not match body")
    return await asyncio.to_thread(
        get_research_journal_store().save_watchlist_item,
        item,
    )


@router.get("/watchlist", response_model=list[WatchlistItem])
async def list_watchlist(active_only: bool = True) -> list[WatchlistItem]:
    return await asyncio.to_thread(
        get_research_journal_store().list_watchlist,
        active_only=active_only,
    )


@router.get("/reminders", response_model=list[ResearchReminder])
async def list_research_reminders(
    as_of: date | None = None,
    horizon_days: Annotated[int, Query(ge=0, le=365)] = 14,
) -> list[ResearchReminder]:
    return await asyncio.to_thread(
        get_research_journal_store().list_due_reminders,
        as_of=as_of or date.today(),
        horizon_days=horizon_days,
    )


__all__ = [
    "FinancialResearchService",
    "ManagementResearchService",
    "calculate_valuation_scenarios",
    "get_financial_snapshot",
    "get_investment_thesis",
    "get_management_comparison",
    "get_research_journal_store",
    "router",
    "save_investment_thesis",
    "save_watchlist_item",
    "set_financial_research_service_for_tests",
    "set_management_research_service_for_tests",
    "set_research_journal_store_for_tests",
]
