"""Build one auditable point-in-time company research snapshot."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.research.management_snapshot import ManagementPeriodSnapshot
from src.research.models import (
    CompanyResearchSnapshot,
    FinancialSnapshot,
    ResearchRunManifest,
    RiskObservation,
    SnapshotComponentResult,
    SourceManifestEntry,
)
from src.research.snapshot_store import ResearchSnapshotStore

FinancialLoader = Callable[[str, date | None], FinancialSnapshot]
ManagementLoader = Callable[[str, int, int], ManagementPeriodSnapshot]
RiskLoader = Callable[[str, datetime], list[RiskObservation]]


class ResearchRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: date | None = None
    year: int | None = Field(default=None, ge=1990, le=2100)
    quarter: int | None = Field(default=None, ge=1, le=4)
    include_management: bool = True
    include_risks: bool = True
    workflow_run_id: str | None = None
    correlation_id: str | None = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned

    def model_post_init(self, _context: object) -> None:
        if (self.year is None) != (self.quarter is None):
            raise ValueError("year and quarter must be provided together")


class ResearchRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: ResearchRunManifest
    snapshot: CompanyResearchSnapshot | None = None


class CompanyResearchOrchestrator:
    def __init__(
        self,
        *,
        store: ResearchSnapshotStore,
        financial_loader: FinancialLoader,
        management_loader: ManagementLoader | None = None,
        risk_loader: RiskLoader | None = None,
    ) -> None:
        self.store = store
        self.financial_loader = financial_loader
        self.management_loader = management_loader
        self.risk_loader = risk_loader

    def run(
        self,
        request: ResearchRunRequest,
        *,
        persist: bool = True,
    ) -> ResearchRunResponse:
        started = datetime.now(UTC)
        started_clock = time.perf_counter()
        run_id = f"research-{uuid.uuid4().hex[:16]}"
        correlation_id = request.correlation_id or request.workflow_run_id or run_id
        cutoff = _knowledge_cutoff(request.as_of)
        components: list[SnapshotComponentResult] = []
        warnings: list[str] = []
        financials: FinancialSnapshot | None = None
        management: ManagementPeriodSnapshot | None = None
        risks: list[RiskObservation] = []

        try:
            financials = self.financial_loader(request.ticker, request.as_of)
            source_count = len(
                {
                    accession
                    for point in financials.metrics
                    for accession in point.source_accession_numbers
                    or ([point.accession_number] if point.accession_number else [])
                }
            )
            components.append(
                SnapshotComponentResult(
                    component="financials",
                    state="partial" if financials.warnings else "complete",
                    reason="; ".join(financials.warnings) if financials.warnings else None,
                    source_count=source_count,
                )
            )
            warnings.extend(financials.warnings)
        except Exception as exc:  # provider boundary: persist degradation, not secrets
            reason = f"financial data unavailable: {type(exc).__name__}"
            components.append(SnapshotComponentResult(component="financials", state="failed", reason=reason))
            warnings.append(reason)

        if request.include_management:
            if request.year is None or request.quarter is None:
                components.append(
                    SnapshotComponentResult(
                        component="management",
                        state="unavailable",
                        reason="year and quarter were not supplied",
                    )
                )
            elif self.management_loader is None:
                components.append(
                    SnapshotComponentResult(
                        component="management",
                        state="unavailable",
                        reason="management provider is not configured",
                    )
                )
            else:
                try:
                    management = self.management_loader(request.ticker, request.year, request.quarter)
                    components.append(SnapshotComponentResult(component="management", state="complete", source_count=1))
                except Exception as exc:
                    reason = f"management data unavailable: {type(exc).__name__}"
                    components.append(SnapshotComponentResult(component="management", state="failed", reason=reason))
                    warnings.append(reason)
        else:
            components.append(
                SnapshotComponentResult(
                    component="management",
                    state="not_requested",
                    reason="management component was not requested",
                )
            )

        if request.include_risks:
            if self.risk_loader is None:
                components.append(
                    SnapshotComponentResult(
                        component="risks",
                        state="unavailable",
                        reason="risk report adapter is not configured",
                    )
                )
            else:
                try:
                    risks = self.risk_loader(request.ticker, cutoff)
                    components.append(
                        SnapshotComponentResult(
                            component="risks",
                            state="complete",
                            source_count=len({item.risk_id for item in risks}),
                        )
                    )
                except Exception as exc:
                    reason = f"risk data unavailable: {type(exc).__name__}"
                    components.append(SnapshotComponentResult(component="risks", state="failed", reason=reason))
                    warnings.append(reason)
        else:
            components.append(
                SnapshotComponentResult(
                    component="risks",
                    state="not_requested",
                    reason="risk component was not requested",
                )
            )

        sources = _build_sources(
            financials,
            management,
            risks,
            cutoff,
            workflow_run_id=request.workflow_run_id,
        )
        fingerprint = _fingerprint(financials, management, risks, sources)
        period = (
            f"{request.year}Q{request.quarter}"
            if request.year is not None and request.quarter is not None
            else cutoff.date().isoformat()
        )
        snapshot_seed = f"{request.ticker}|{period}|{cutoff.isoformat()}|{fingerprint}"
        snapshot_id = f"snapshot-{hashlib.sha256(snapshot_seed.encode()).hexdigest()[:16]}"
        snapshot = CompanyResearchSnapshot(
            snapshot_id=snapshot_id,
            correlation_id=correlation_id,
            ticker=request.ticker,
            period=period,
            as_of=cutoff,
            source_fingerprint=fingerprint,
            financials=financials,
            management=management,
            risks=risks,
            components=components,
            sources=sources,
            warnings=warnings,
        )
        saved_snapshot = self.store.save_snapshot(snapshot) if persist else snapshot
        state = _run_state(components)
        completed = datetime.now(UTC)
        manifest = ResearchRunManifest(
            run_id=run_id,
            correlation_id=correlation_id,
            ticker=request.ticker,
            requested_as_of=cutoff,
            started_at=started,
            completed_at=completed,
            state=state,
            snapshot_id=saved_snapshot.snapshot_id,
            components=components,
            duration_ms=max(0, round((time.perf_counter() - started_clock) * 1000)),
            warnings=warnings,
        )
        if persist:
            self.store.save_run(manifest)
        return ResearchRunResponse(manifest=manifest, snapshot=saved_snapshot)


def _knowledge_cutoff(value: date | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    selected = value
    return datetime(selected.year, selected.month, selected.day, 23, 59, 59, tzinfo=UTC)


def _build_sources(
    financials: FinancialSnapshot | None,
    management: ManagementPeriodSnapshot | None,
    risks: list[RiskObservation],
    cutoff: datetime,
    *,
    workflow_run_id: str | None,
) -> list[SourceManifestEntry]:
    sources: list[SourceManifestEntry] = []
    if financials is not None:
        accessions: dict[str, date | None] = {}
        for point in financials.metrics:
            ids = point.source_accession_numbers or ([point.accession_number] if point.accession_number else [])
            for accession in ids:
                accessions[accession] = point.filed_at
        for accession, filed_at in sorted(accessions.items()):
            source_as_of = datetime(filed_at.year, filed_at.month, filed_at.day, tzinfo=UTC) if filed_at else cutoff
            sources.append(
                SourceManifestEntry(
                    source_id=accession,
                    source_type="sec_filing",
                    provider="SEC",
                    as_of=source_as_of,
                )
            )
    if management is not None:
        sources.append(
            SourceManifestEntry(
                source_id=management.transcript_id,
                source_type="transcript",
                provider=management.provider,
                as_of=management.published_at or cutoff,
                url=management.source_url,
                metadata={"year": management.year, "quarter": management.quarter},
            )
        )
    if risks and workflow_run_id:
        sources.append(
            SourceManifestEntry(
                source_id=workflow_run_id,
                source_type="risk_report",
                provider="FinRisk",
                as_of=cutoff,
                metadata={
                    "risk_count": len(risks),
                    "evidence_count": len(
                        {
                            evidence_id
                            for risk in risks
                            for evidence_id in risk.evidence_ids
                        }
                    ),
                },
            )
        )
    return sources


def _fingerprint(
    financials: FinancialSnapshot | None,
    management: ManagementPeriodSnapshot | None,
    risks: list[RiskObservation],
    sources: list[SourceManifestEntry],
) -> str:
    payload = {
        "financials": (financials.model_dump(mode="json", exclude={"as_of"}) if financials else None),
        "management": management.model_dump(mode="json") if management else None,
        "risks": [item.model_dump(mode="json") for item in risks],
        "sources": [item.model_dump(mode="json") for item in sources],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _run_state(components: list[SnapshotComponentResult]) -> str:
    states = {
        item.state for item in components if item.state != "not_requested"
    }
    if not states.intersection({"complete", "partial"}):
        return "failed"
    if states <= {"complete"}:
        return "completed"
    return "partial"


__all__ = ["CompanyResearchOrchestrator", "ResearchRunRequest", "ResearchRunResponse"]
