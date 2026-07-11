"""Point-in-time financial research endpoints."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.research import FinancialSnapshot, FinancialSnapshotBuilder
from src.research.alert_store import (
    AlertActionRequest,
    AlertStatus,
    ResearchAlert,
    ResearchAlertStore,
)
from src.research.change_detection import (
    ChangeReviewRequest,
    ResearchChange,
    ResearchChangeSet,
    detect_research_changes,
)
from src.research.change_store import ResearchChangeStore
from src.research.comparison import (
    CompanyComparisonRequest,
    CompanyComparisonResponse,
    PeerAnalysisRequest,
    PeerAnalysisResponse,
    ResearchQueueResponse,
    build_peer_analysis,
    build_research_queue,
    compare_company_snapshots,
)
from src.research.expectations import (
    ExpectationComparison,
    ExpectationImportResult,
    ExpectationPoint,
    ExpectationStore,
    compare_expectation_to_actual,
)
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
    ManagementPeriodSnapshot,
    build_management_snapshot,
    compare_management_snapshots,
)
from src.research.models import (
    CompanyResearchSnapshot,
    FinancialMetricPoint,
    ResearchRunManifest,
)
from src.research.monitor import (
    MonitorScanRequest,
    MonitorScanResponse,
    WatchlistMonitor,
)
from src.research.orchestrator import (
    CompanyResearchOrchestrator,
    ResearchRunRequest,
    ResearchRunResponse,
)
from src.research.peer_groups import (
    PeerCandidate,
    PeerCandidateRequest,
    PeerGroup,
    PeerGroupInput,
    PeerGroupStore,
    suggest_peer_candidates,
)
from src.research.post_earnings import (
    ConfirmPostEarningsReviewRequest,
    PostEarningsDraftRequest,
    PostEarningsReviewDraft,
    PostEarningsReviewStore,
    build_post_earnings_review_draft,
)
from src.research.risk_adapter import risk_observations_from_report
from src.research.snapshot_store import ResearchSnapshotStore
from src.research.valuation import (
    DiscountedCashFlowRequest,
    DiscountedCashFlowResponse,
    MultipleValuationRequest,
    MultipleValuationResponse,
    ScenarioValuationRequest,
    ScenarioValuationResponse,
    SensitivityMatrixRequest,
    SensitivityMatrixResponse,
    calculate_discounted_cash_flow,
    calculate_multiple_valuation,
    calculate_scenario_valuation,
    calculate_sensitivity_matrix,
)
from src.research.valuation_store import (
    ValuationAssumptionSnapshot,
    ValuationAssumptionStore,
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
        industry_template: str = "general",
        restatement_policy: Literal[
            "latest_known", "original", "amended_only"
        ] = "latest_known",
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
        return FinancialSnapshotBuilder(
            industry_template,
            restatement_policy=restatement_policy,
        ).build(
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
        current = build_management_snapshot(provider.get_transcript(ticker.upper(), year, quarter))
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
_snapshot_store: ResearchSnapshotStore | None = None
_research_orchestrator: CompanyResearchOrchestrator | None = None
_change_store: ResearchChangeStore | None = None
_expectation_store: ExpectationStore | None = None
_alert_store: ResearchAlertStore | None = None
_watchlist_monitor: WatchlistMonitor | None = None
_post_earnings_store: PostEarningsReviewStore | None = None
_peer_group_store: PeerGroupStore | None = None
_valuation_assumption_store: ValuationAssumptionStore | None = None


class ExpectationCSVImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class ResearchQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(min_length=1, max_length=50)


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


def get_research_snapshot_store() -> ResearchSnapshotStore:
    global _snapshot_store
    if _snapshot_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _snapshot_store = ResearchSnapshotStore(path)
    return _snapshot_store


def set_research_snapshot_store_for_tests(
    store: ResearchSnapshotStore | None,
) -> None:
    global _snapshot_store, _research_orchestrator
    _snapshot_store = store
    _research_orchestrator = None


def get_company_research_orchestrator() -> CompanyResearchOrchestrator:
    global _research_orchestrator
    if _research_orchestrator is None:
        _research_orchestrator = CompanyResearchOrchestrator(
            store=get_research_snapshot_store(),
            financial_loader=_load_financial_snapshot,
            management_loader=_load_management_snapshot,
        )
    return _research_orchestrator


def _load_financial_snapshot(ticker: str, as_of: date | None) -> FinancialSnapshot:
    return _service.build_snapshot(ticker, as_of)


def _load_management_snapshot(ticker: str, year: int, quarter: int) -> ManagementPeriodSnapshot:
    return _management_service.compare(
        ticker=ticker,
        year=year,
        quarter=quarter,
    ).current


def set_company_research_orchestrator_for_tests(
    orchestrator: CompanyResearchOrchestrator | None,
) -> None:
    global _research_orchestrator
    _research_orchestrator = orchestrator


def get_research_change_store() -> ResearchChangeStore:
    global _change_store
    if _change_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _change_store = ResearchChangeStore(path)
    return _change_store


def set_research_change_store_for_tests(store: ResearchChangeStore | None) -> None:
    global _change_store
    _change_store = store


def get_expectation_store() -> ExpectationStore:
    global _expectation_store
    if _expectation_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _expectation_store = ExpectationStore(path)
    return _expectation_store


def set_expectation_store_for_tests(store: ExpectationStore | None) -> None:
    global _expectation_store
    _expectation_store = store


def get_research_alert_store() -> ResearchAlertStore:
    global _alert_store
    if _alert_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _alert_store = ResearchAlertStore(path)
    return _alert_store


def set_research_alert_store_for_tests(store: ResearchAlertStore | None) -> None:
    global _alert_store, _watchlist_monitor
    _alert_store = store
    _watchlist_monitor = None


def get_watchlist_monitor() -> WatchlistMonitor:
    global _watchlist_monitor
    if _watchlist_monitor is None:
        _watchlist_monitor = WatchlistMonitor(
            orchestrator=get_company_research_orchestrator(),
            snapshot_store=get_research_snapshot_store(),
            change_store=get_research_change_store(),
            alert_store=get_research_alert_store(),
            journal_store=get_research_journal_store(),
        )
    return _watchlist_monitor


def set_watchlist_monitor_for_tests(monitor: WatchlistMonitor | None) -> None:
    global _watchlist_monitor
    _watchlist_monitor = monitor


def get_post_earnings_review_store() -> PostEarningsReviewStore:
    global _post_earnings_store
    if _post_earnings_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _post_earnings_store = PostEarningsReviewStore(path)
    return _post_earnings_store


def set_post_earnings_review_store_for_tests(
    store: PostEarningsReviewStore | None,
) -> None:
    global _post_earnings_store
    _post_earnings_store = store


def get_peer_group_store() -> PeerGroupStore:
    global _peer_group_store
    if _peer_group_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _peer_group_store = PeerGroupStore(path)
    return _peer_group_store


def set_peer_group_store_for_tests(store: PeerGroupStore | None) -> None:
    global _peer_group_store
    _peer_group_store = store


def get_valuation_assumption_store() -> ValuationAssumptionStore:
    global _valuation_assumption_store
    if _valuation_assumption_store is None:
        path = Path(
            os.environ.get(
                "RESEARCH_SNAPSHOT_PATH",
                ".cache/research_snapshots.sqlite",
            )
        )
        _valuation_assumption_store = ValuationAssumptionStore(path)
    return _valuation_assumption_store


def set_valuation_assumption_store_for_tests(
    store: ValuationAssumptionStore | None,
) -> None:
    global _valuation_assumption_store
    _valuation_assumption_store = store


@router.post(
    "/runs",
    response_model=ResearchRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_research_run(
    request: ResearchRunRequest,
) -> ResearchRunResponse:
    """Build and persist one point-in-time company research snapshot."""
    orchestrator = get_company_research_orchestrator()
    if request.workflow_run_id:
        from src.api.workflows import get_run_store

        state = await get_run_store().get(request.workflow_run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="workflow run not found")
        company = getattr(state, "company", None)
        workflow_ticker = str(getattr(company, "ticker", "")).upper()
        if workflow_ticker and workflow_ticker != request.ticker:
            raise HTTPException(
                status_code=422,
                detail="workflow run ticker does not match research ticker",
            )
        risks = risk_observations_from_report(getattr(state, "report_v16", None))
        orchestrator = CompanyResearchOrchestrator(
            store=get_research_snapshot_store(),
            financial_loader=_load_financial_snapshot,
            management_loader=_load_management_snapshot,
            risk_loader=lambda _ticker, _cutoff: risks,
        )
    return await asyncio.to_thread(orchestrator.run, request)


@router.get("/runs/{run_id}", response_model=ResearchRunManifest)
async def get_company_research_run(run_id: str) -> ResearchRunManifest:
    run = await asyncio.to_thread(get_research_snapshot_store().get_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return run


@router.get("/snapshots/{snapshot_id}", response_model=CompanyResearchSnapshot)
async def get_company_research_snapshot(
    snapshot_id: str,
) -> CompanyResearchSnapshot:
    snapshot = await asyncio.to_thread(
        get_research_snapshot_store().get_snapshot,
        snapshot_id,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="research snapshot not found")
    return snapshot


@router.get("/snapshots", response_model=list[CompanyResearchSnapshot])
async def list_company_research_snapshots(
    ticker: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CompanyResearchSnapshot]:
    return await asyncio.to_thread(
        get_research_snapshot_store().list_snapshots,
        ticker,
        limit=limit,
    )


@router.get("/changes/{ticker}", response_model=ResearchChangeSet)
async def get_company_research_changes(
    ticker: str,
    from_snapshot_id: str | None = None,
    to_snapshot_id: str | None = None,
) -> ResearchChangeSet:
    store = get_research_snapshot_store()
    if (from_snapshot_id is None) != (to_snapshot_id is None):
        raise HTTPException(
            status_code=422,
            detail="from_snapshot_id and to_snapshot_id must be provided together",
        )
    if from_snapshot_id and to_snapshot_id:
        previous = await asyncio.to_thread(store.get_snapshot, from_snapshot_id)
        current = await asyncio.to_thread(store.get_snapshot, to_snapshot_id)
    else:
        snapshots = await asyncio.to_thread(store.list_snapshots, ticker, limit=2)
        if len(snapshots) < 2:
            raise HTTPException(
                status_code=404,
                detail="at least two research snapshots are required",
            )
        current, previous = snapshots
    if previous is None or current is None:
        raise HTTPException(status_code=404, detail="research snapshot not found")
    if current.ticker != ticker.upper() or previous.ticker != ticker.upper():
        raise HTTPException(status_code=422, detail="snapshot ticker mismatch")
    try:
        change_set = await asyncio.to_thread(
            detect_research_changes,
            previous,
            current,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await asyncio.to_thread(
        get_research_change_store().save_change_set,
        change_set,
    )


@router.post("/changes/{change_id}/review", response_model=ResearchChange)
async def review_company_research_change(
    change_id: str,
    review: ChangeReviewRequest,
) -> ResearchChange:
    try:
        return await asyncio.to_thread(
            get_research_change_store().review_change,
            change_id,
            review,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="research change not found") from exc


@router.post(
    "/expectations",
    response_model=ExpectationPoint,
    status_code=status.HTTP_201_CREATED,
)
async def save_research_expectation(point: ExpectationPoint) -> ExpectationPoint:
    saved, _created = await asyncio.to_thread(get_expectation_store().save, point)
    return saved


@router.get("/expectations", response_model=list[ExpectationPoint])
async def list_research_expectations(
    ticker: str,
    metric: str | None = None,
    fiscal_period: str | None = None,
    known_on_or_before: datetime | None = None,
) -> list[ExpectationPoint]:
    return await asyncio.to_thread(
        get_expectation_store().list,
        ticker=ticker,
        metric=metric,
        fiscal_period=fiscal_period,
        known_on_or_before=known_on_or_before,
    )


@router.post(
    "/expectations/import-csv",
    response_model=ExpectationImportResult,
)
async def import_research_expectations(
    request: ExpectationCSVImportRequest,
) -> ExpectationImportResult:
    try:
        return await asyncio.to_thread(
            get_expectation_store().import_csv,
            request.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/expectations/{expectation_id}/compare",
    response_model=ExpectationComparison,
)
async def compare_research_expectation(
    expectation_id: str,
    snapshot_id: str,
) -> ExpectationComparison:
    expectation = await asyncio.to_thread(
        get_expectation_store().get,
        expectation_id,
    )
    snapshot = await asyncio.to_thread(
        get_research_snapshot_store().get_snapshot,
        snapshot_id,
    )
    if expectation is None or snapshot is None:
        raise HTTPException(status_code=404, detail="expectation or snapshot not found")
    if expectation.ticker != snapshot.ticker or snapshot.financials is None:
        raise HTTPException(status_code=422, detail="expectation and snapshot mismatch")
    candidates = [
        point
        for point in snapshot.financials.metrics
        if point.metric == expectation.metric
        and point.unit == expectation.unit
        and _financial_period_label(point) == expectation.fiscal_period
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail="matching actual metric not found")
    actual = max(candidates, key=lambda point: (point.filed_at or date.min, point.period_end))
    try:
        return compare_expectation_to_actual(expectation, actual)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _financial_period_label(point: FinancialMetricPoint) -> str:
    if point.fiscal_year and point.fiscal_period:
        return f"{point.fiscal_year}{point.fiscal_period}"
    return point.period_end.isoformat()


@router.post("/monitor/scan", response_model=MonitorScanResponse)
async def scan_research_watchlist(
    request: MonitorScanRequest,
) -> MonitorScanResponse:
    return await asyncio.to_thread(get_watchlist_monitor().scan, request)


@router.get("/alerts", response_model=list[ResearchAlert])
async def list_research_alerts(
    ticker: str | None = None,
    alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
) -> list[ResearchAlert]:
    return await asyncio.to_thread(
        get_research_alert_store().list_alerts,
        ticker=ticker,
        status=alert_status,
    )


@router.post("/alerts/{alert_id}/action", response_model=ResearchAlert)
async def act_on_research_alert(
    alert_id: str,
    request: AlertActionRequest,
) -> ResearchAlert:
    try:
        return await asyncio.to_thread(
            get_research_alert_store().act,
            alert_id,
            request,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="research alert not found") from exc


@router.post(
    "/post-earnings/drafts",
    response_model=PostEarningsReviewDraft,
    status_code=status.HTTP_201_CREATED,
)
async def create_post_earnings_review_draft(
    request: PostEarningsDraftRequest,
) -> PostEarningsReviewDraft:
    thesis = await asyncio.to_thread(
        get_research_journal_store().get_thesis,
        request.thesis_id,
    )
    previous = await asyncio.to_thread(
        get_research_snapshot_store().get_snapshot,
        request.from_snapshot_id,
    )
    current = await asyncio.to_thread(
        get_research_snapshot_store().get_snapshot,
        request.to_snapshot_id,
    )
    if thesis is None or previous is None or current is None:
        raise HTTPException(status_code=404, detail="thesis or snapshot not found")
    try:
        change_set = detect_research_changes(previous, current)
        comparisons = []
        for expectation_id in request.expectation_ids:
            expectation = get_expectation_store().get(expectation_id)
            if expectation is None or current.financials is None:
                raise ValueError(f"expectation unavailable: {expectation_id}")
            candidates = [
                point
                for point in current.financials.metrics
                if point.metric == expectation.metric
                and point.unit == expectation.unit
                and _financial_period_label(point) == expectation.fiscal_period
            ]
            if not candidates:
                raise ValueError(f"matching actual unavailable for expectation: {expectation_id}")
            actual = max(
                candidates,
                key=lambda point: (point.filed_at or date.min, point.period_end),
            )
            comparisons.append(compare_expectation_to_actual(expectation, actual))
        draft = build_post_earnings_review_draft(
            thesis=thesis,
            previous=previous,
            current=current,
            changes=change_set.changes,
            expectation_comparisons=comparisons,
            locked_assumptions=request.locked_assumptions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await asyncio.to_thread(get_post_earnings_review_store().save, draft)


@router.get(
    "/post-earnings/drafts",
    response_model=list[PostEarningsReviewDraft],
)
async def list_post_earnings_review_drafts(
    ticker: str | None = None,
) -> list[PostEarningsReviewDraft]:
    return await asyncio.to_thread(
        get_post_earnings_review_store().list,
        ticker=ticker,
    )


@router.get(
    "/post-earnings/drafts/{draft_id}",
    response_model=PostEarningsReviewDraft,
)
async def get_post_earnings_review_draft(
    draft_id: str,
) -> PostEarningsReviewDraft:
    draft = await asyncio.to_thread(get_post_earnings_review_store().get, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="post-earnings draft not found")
    return draft


@router.post(
    "/post-earnings/drafts/{draft_id}/confirm",
    response_model=PostEarningsReviewDraft,
)
async def confirm_post_earnings_review(
    draft_id: str,
    request: ConfirmPostEarningsReviewRequest,
) -> PostEarningsReviewDraft:
    try:
        return await asyncio.to_thread(
            get_post_earnings_review_store().confirm,
            draft_id,
            request,
            get_research_journal_store(),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="post-earnings draft or thesis not found",
        ) from exc


@router.post("/comparison", response_model=CompanyComparisonResponse)
async def compare_research_companies(
    request: CompanyComparisonRequest,
) -> CompanyComparisonResponse:
    snapshots = []
    for snapshot_id in request.snapshot_ids:
        snapshot = await asyncio.to_thread(
            get_research_snapshot_store().get_snapshot,
            snapshot_id,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail=f"research snapshot not found: {snapshot_id}",
            )
        snapshots.append(snapshot)
    try:
        return compare_company_snapshots(
            snapshots,
            metrics=request.metrics,
            period_kind=request.period_kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/peer-groups", response_model=PeerGroup, status_code=status.HTTP_201_CREATED)
async def create_peer_group(request: PeerGroupInput) -> PeerGroup:
    return await asyncio.to_thread(get_peer_group_store().save, request)


@router.get("/peer-groups", response_model=list[PeerGroup])
async def list_peer_groups() -> list[PeerGroup]:
    return await asyncio.to_thread(get_peer_group_store().list)


@router.get("/peer-groups/{peer_group_id}", response_model=PeerGroup)
async def get_peer_group(peer_group_id: str) -> PeerGroup:
    group = await asyncio.to_thread(get_peer_group_store().get, peer_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="peer group not found")
    return group


@router.put("/peer-groups/{peer_group_id}", response_model=PeerGroup)
async def update_peer_group(
    peer_group_id: str,
    request: PeerGroupInput,
) -> PeerGroup:
    try:
        return await asyncio.to_thread(
            get_peer_group_store().update,
            peer_group_id,
            request,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="peer group not found") from exc


@router.post(
    "/peer-groups/{peer_group_id}/comparison",
    response_model=CompanyComparisonResponse,
)
async def compare_peer_group(
    peer_group_id: str,
    request: CompanyComparisonRequest,
) -> CompanyComparisonResponse:
    group = await asyncio.to_thread(get_peer_group_store().get, peer_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="peer group not found")
    snapshots = []
    member_tickers = {member.ticker for member in group.members}
    for snapshot_id in request.snapshot_ids:
        snapshot = await asyncio.to_thread(
            get_research_snapshot_store().get_snapshot,
            snapshot_id,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"snapshot not found: {snapshot_id}")
        if snapshot.ticker not in member_tickers:
            raise HTTPException(status_code=422, detail=f"{snapshot.ticker} is not in the peer group")
        snapshots.append(snapshot)
    try:
        return compare_company_snapshots(
            snapshots,
            metrics=request.metrics,
            period_kind=request.period_kind,
            strict_as_of=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/peer-groups/{peer_group_id}/analysis",
    response_model=PeerAnalysisResponse,
)
async def analyze_peer_group(
    peer_group_id: str,
    request: PeerAnalysisRequest,
) -> PeerAnalysisResponse:
    group = await asyncio.to_thread(get_peer_group_store().get, peer_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="peer group not found")
    member_tickers = {member.ticker for member in group.members}
    snapshots = []
    for snapshot_id in request.snapshot_ids:
        snapshot = await asyncio.to_thread(
            get_research_snapshot_store().get_snapshot,
            snapshot_id,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"snapshot not found: {snapshot_id}")
        if snapshot.ticker not in member_tickers:
            raise HTTPException(status_code=422, detail=f"{snapshot.ticker} is not in the peer group")
        snapshots.append(snapshot)
    expectations = {
        snapshot.ticker: await asyncio.to_thread(
            get_expectation_store().list,
            ticker=snapshot.ticker,
        )
        for snapshot in snapshots
    }
    try:
        return build_peer_analysis(
            snapshots,
            request=request,
            expectations_by_ticker=expectations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/peer-groups/{peer_group_id}/candidates",
    response_model=list[PeerCandidate],
)
async def get_peer_group_candidates(
    peer_group_id: str,
    request: PeerCandidateRequest,
) -> list[PeerCandidate]:
    group = await asyncio.to_thread(get_peer_group_store().get, peer_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="peer group not found")
    tickers = request.tickers
    if not tickers:
        watchlist = await asyncio.to_thread(get_research_journal_store().list_watchlist)
        tickers = [item.ticker for item in watchlist]
    from src.data.sec_client import SECClient
    from src.data.ticker_resolver import TickerResolver

    client = SECClient()
    try:
        return await asyncio.to_thread(
            suggest_peer_candidates,
            base_ticker=group.base_ticker,
            candidate_tickers=tickers,
            resolver=TickerResolver(),
            submissions_fetcher=client.get_submissions,
        )
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"peer candidate data unavailable: {type(exc).__name__}",
        ) from exc


@router.delete("/peer-groups/{peer_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_peer_group(peer_group_id: str) -> None:
    deleted = await asyncio.to_thread(get_peer_group_store().delete, peer_group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="peer group not found")


@router.post("/research-queue", response_model=ResearchQueueResponse)
async def build_company_research_queue(
    request: ResearchQueueRequest,
) -> ResearchQueueResponse:
    change_sets = []
    for ticker in request.tickers:
        snapshots = await asyncio.to_thread(
            get_research_snapshot_store().list_snapshots,
            ticker,
            limit=2,
        )
        if len(snapshots) < 2:
            continue
        current, previous = snapshots
        if previous.as_of >= current.as_of:
            continue
        change_set = detect_research_changes(previous, current)
        change_sets.append(get_research_change_store().save_change_set(change_set))
    return build_research_queue(change_sets)


@router.get(
    "/financials/{ticker}",
    response_model=FinancialSnapshot,
)
async def get_financial_snapshot(
    ticker: str,
    as_of: Annotated[date | None, Query()] = None,
    industry_template: str = "general",
    restatement_policy: Literal[
        "latest_known", "original", "amended_only"
    ] = "latest_known",
) -> FinancialSnapshot:
    """Return normalized SEC facts known on or before ``as_of``."""
    try:
        return await asyncio.to_thread(
            _service.build_snapshot,
            ticker,
            as_of,
            industry_template,
            restatement_policy,
        )
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
    result = calculate_scenario_valuation(request)
    saved = await asyncio.to_thread(
        get_valuation_assumption_store().save,
        ticker=request.ticker,
        kind="scenario",
        request=request.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        evidence_ids=request.evidence_ids,
    )
    return result.model_copy(
        update={"assumption_snapshot_id": saved.assumption_snapshot_id}
    )


@router.post(
    "/valuation/sensitivity",
    response_model=SensitivityMatrixResponse,
)
async def calculate_valuation_sensitivity(
    request: SensitivityMatrixRequest,
) -> SensitivityMatrixResponse:
    try:
        result = calculate_sensitivity_matrix(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved = await asyncio.to_thread(
        get_valuation_assumption_store().save,
        ticker=request.ticker,
        kind="sensitivity",
        request=request.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        evidence_ids=[],
    )
    return result.model_copy(
        update={"assumption_snapshot_id": saved.assumption_snapshot_id}
    )


@router.post("/valuation/multiple", response_model=MultipleValuationResponse)
async def calculate_valuation_multiple(
    request: MultipleValuationRequest,
) -> MultipleValuationResponse:
    result = calculate_multiple_valuation(request)
    saved = await asyncio.to_thread(
        get_valuation_assumption_store().save,
        ticker=request.ticker,
        kind="multiple",
        request=request.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        evidence_ids=request.evidence_ids,
    )
    return result.model_copy(
        update={"assumption_snapshot_id": saved.assumption_snapshot_id}
    )


@router.post("/valuation/dcf", response_model=DiscountedCashFlowResponse)
async def calculate_valuation_dcf(
    request: DiscountedCashFlowRequest,
) -> DiscountedCashFlowResponse:
    result = calculate_discounted_cash_flow(request)
    saved = await asyncio.to_thread(
        get_valuation_assumption_store().save,
        ticker=request.ticker,
        kind="dcf",
        request=request.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        evidence_ids=request.evidence_ids,
    )
    return result.model_copy(
        update={"assumption_snapshot_id": saved.assumption_snapshot_id}
    )


@router.get(
    "/valuation/history/{ticker}",
    response_model=list[ValuationAssumptionSnapshot],
)
async def list_valuation_assumption_history(
    ticker: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ValuationAssumptionSnapshot]:
    return await asyncio.to_thread(
        get_valuation_assumption_store().list,
        ticker,
        limit=limit,
    )


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
    "act_on_research_alert",
    "build_company_research_queue",
    "calculate_valuation_scenarios",
    "calculate_valuation_sensitivity",
    "compare_research_companies",
    "compare_research_expectation",
    "confirm_post_earnings_review",
    "create_company_research_run",
    "create_post_earnings_review_draft",
    "get_company_research_changes",
    "get_company_research_orchestrator",
    "get_company_research_run",
    "get_company_research_snapshot",
    "get_expectation_store",
    "get_financial_snapshot",
    "get_investment_thesis",
    "get_management_comparison",
    "get_post_earnings_review_draft",
    "get_post_earnings_review_store",
    "get_research_alert_store",
    "get_research_change_store",
    "get_research_journal_store",
    "get_research_snapshot_store",
    "get_watchlist_monitor",
    "import_research_expectations",
    "list_company_research_snapshots",
    "list_post_earnings_review_drafts",
    "list_research_alerts",
    "list_research_expectations",
    "review_company_research_change",
    "router",
    "save_investment_thesis",
    "save_research_expectation",
    "save_watchlist_item",
    "scan_research_watchlist",
    "set_company_research_orchestrator_for_tests",
    "set_expectation_store_for_tests",
    "set_financial_research_service_for_tests",
    "set_management_research_service_for_tests",
    "set_post_earnings_review_store_for_tests",
    "set_research_alert_store_for_tests",
    "set_research_change_store_for_tests",
    "set_research_journal_store_for_tests",
    "set_research_snapshot_store_for_tests",
    "set_watchlist_monitor_for_tests",
]
