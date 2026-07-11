"""Deterministic, evidence-linked change detection between research snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.management_snapshot import compare_management_snapshots
from src.research.models import CompanyResearchSnapshot, FinancialMetricPoint

ChangeCategory = Literal["financial", "risk", "guidance", "management", "evidence"]
ChangeStatus = Literal["new", "persistent", "strengthened", "weakened", "resolved"]
Materiality = Literal["low", "medium", "high", "unknown"]
ReviewStatus = Literal["unreviewed", "confirmed", "ignored", "needs_review"]


class ResearchChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    ticker: str
    category: ChangeCategory
    key: str
    status: ChangeStatus
    materiality: Materiality
    before: Any | None = None
    after: Any | None = None
    before_evidence_ids: list[str] = Field(default_factory=list)
    after_evidence_ids: list[str] = Field(default_factory=list)
    detection_method: str
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    analyst_review_status: ReviewStatus = "unreviewed"


class ResearchChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    from_snapshot_id: str
    to_snapshot_id: str
    correlation_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    changes: list[ResearchChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChangeReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["confirmed", "ignored", "needs_review"]
    notes: str | None = None


def detect_research_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
    *,
    source_stale_after_days: int | None = None,
) -> ResearchChangeSet:
    """Compare two immutable snapshots using deterministic rules."""
    if previous.ticker != current.ticker:
        raise ValueError("research snapshots must belong to the same ticker")
    if previous.as_of >= current.as_of:
        raise ValueError("current snapshot must be newer than previous snapshot")
    if source_stale_after_days is not None and source_stale_after_days < 1:
        raise ValueError("source_stale_after_days must be positive")

    changes = [
        *_financial_changes(previous, current),
        *_management_changes(previous, current),
        *_risk_changes(previous, current),
        *_evidence_changes(previous, current),
        *_source_quality_changes(
            previous,
            current,
            stale_after_days=source_stale_after_days,
        ),
    ]
    return ResearchChangeSet(
        ticker=current.ticker,
        from_snapshot_id=previous.snapshot_id,
        to_snapshot_id=current.snapshot_id,
        correlation_id=current.correlation_id,
        warnings=_comparison_warnings(previous, current),
        changes=sorted(
            changes,
            key=lambda item: (
                {"high": 0, "medium": 1, "unknown": 2, "low": 3}[item.materiality],
                item.category,
                item.key,
            ),
        ),
    )


def _financial_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
) -> list[ResearchChange]:
    if previous.financials is None or current.financials is None:
        return []
    before = _latest_financial_points(previous.financials.metrics)
    after = _latest_financial_points(current.financials.metrics)
    changes: list[ResearchChange] = []
    for key in sorted(before.keys() | after.keys()):
        old = before.get(key)
        new = after.get(key)
        if old is None and new is not None:
            evidence = _financial_evidence(new)
            changes.append(
                _change(
                    ticker=current.ticker,
                    category="financial",
                    key=f"{key[0]}:{key[1]}",
                    status="new",
                    materiality="unknown",
                    before=None,
                    after=_point_value(new),
                    before_evidence=[],
                    after_evidence=evidence,
                    method="deterministic_metric_presence",
                    explanation=f"{key[0]} became available for {key[1]} periods.",
                    confidence=1.0,
                )
            )
            continue
        if old is None or new is None or old.value == new.value:
            continue
        percent = (new.value - old.value) / abs(old.value) if old.value else None
        direction: ChangeStatus = "strengthened" if new.value > old.value else "weakened"
        materiality = _numeric_materiality(percent)
        before_evidence = _financial_evidence(old)
        after_evidence = _financial_evidence(new)
        materiality = _evidence_safe_materiality(materiality, before_evidence, after_evidence)
        changes.append(
            _change(
                ticker=current.ticker,
                category="financial",
                key=f"{key[0]}:{key[1]}",
                status=direction,
                materiality=materiality,
                before=_point_value(old),
                after={**_point_value(new), "percent_change": percent},
                before_evidence=before_evidence,
                after_evidence=after_evidence,
                method="deterministic_period_comparison",
                explanation=(f"{key[0]} changed from {old.value:g} to {new.value:g} for the latest {key[1]} period."),
                confidence=1.0,
            )
        )
    return changes


def _management_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
) -> list[ResearchChange]:
    if previous.management is None or current.management is None:
        return []
    changes: list[ResearchChange] = []
    for signal in compare_management_snapshots(previous.management, current.management):
        category: ChangeCategory = (
            "guidance"
            if signal.dimension == "guidance_signal"
            or signal.dimension.startswith("guidance_range:")
            else "management"
        )
        status: ChangeStatus
        if signal.direction in {"strengthened", "increased"}:
            status = "strengthened"
        elif signal.direction in {"weakened", "decreased"}:
            status = "weakened"
        else:
            status = "persistent"
        evidence = signal.evidence_ids
        materiality: Materiality = "high" if category == "guidance" else "medium"
        materiality = _evidence_safe_materiality(materiality, evidence, evidence)
        changes.append(
            _change(
                ticker=current.ticker,
                category=category,
                key=signal.dimension,
                status=status,
                materiality=materiality,
                before=(
                    {
                        "value": signal.previous_value,
                        "quotes": signal.previous_quotes,
                    }
                    if signal.previous_quotes
                    else signal.previous_value
                ),
                after=(
                    {
                        "value": signal.current_value,
                        "quotes": signal.current_quotes,
                    }
                    if signal.current_quotes
                    else signal.current_value
                ),
                before_evidence=evidence,
                after_evidence=evidence,
                method="deterministic_management_signal_comparison",
                explanation=(f"{signal.dimension} changed from {signal.previous_value} to {signal.current_value}."),
                confidence=1.0,
            )
        )
    return changes


def _risk_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
) -> list[ResearchChange]:
    if not _component_comparable(previous, "risks") or not _component_comparable(
        current, "risks"
    ):
        return []
    before = {item.risk_id: item for item in previous.risks}
    after = {item.risk_id: item for item in current.risks}
    changes: list[ResearchChange] = []
    for risk_id in sorted(before.keys() | after.keys()):
        old = before.get(risk_id)
        new = after.get(risk_id)
        if old is None and new is not None:
            status: ChangeStatus = "new"
        elif old is not None and new is None:
            status = "resolved"
        elif old is not None and new is not None:
            if old.model_dump() == new.model_dump():
                continue
            status = new.status if new.status in {"strengthened", "weakened", "resolved"} else "persistent"
        else:
            continue
        before_evidence = old.evidence_ids if old else []
        after_evidence = new.evidence_ids if new else []
        materiality = _evidence_safe_materiality("medium", before_evidence, after_evidence)
        changes.append(
            _change(
                ticker=current.ticker,
                category="risk",
                key=risk_id,
                status=status,
                materiality=materiality,
                before=old.model_dump(mode="json") if old else None,
                after=new.model_dump(mode="json") if new else None,
                before_evidence=before_evidence,
                after_evidence=after_evidence,
                method="deterministic_risk_identity_comparison",
                explanation=f"Risk {risk_id} is {status} in the current snapshot.",
                confidence=1.0,
            )
        )
    return changes


def _evidence_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
) -> list[ResearchChange]:
    if any(item.state in {"failed", "unavailable"} for item in current.components):
        return []
    before = {item.source_id for item in previous.sources}
    after = {item.source_id for item in current.sources}
    removed = sorted(before - after)
    if not removed or len(after) >= len(before):
        return []
    return [
        _change(
            ticker=current.ticker,
            category="evidence",
            key="source_coverage",
            status="weakened",
            materiality="unknown",
            before={"source_count": len(before)},
            after={"source_count": len(after), "removed_source_ids": removed},
            before_evidence=sorted(before),
            after_evidence=sorted(after),
            method="deterministic_source_manifest_comparison",
            explanation="One or more previously available sources are absent.",
            confidence=1.0,
        )
    ]


def _source_quality_changes(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
    *,
    stale_after_days: int | None,
) -> list[ResearchChange]:
    changes: list[ResearchChange] = []
    if stale_after_days is not None:
        before = {item.source_id: item for item in previous.sources}
        for source in current.sources:
            age_days = (current.as_of - source.as_of).days
            old = before.get(source.source_id)
            old_age = (previous.as_of - old.as_of).days if old else None
            if age_days <= stale_after_days or (
                old_age is not None and old_age > stale_after_days
            ):
                continue
            changes.append(
                _change(
                    ticker=current.ticker,
                    category="evidence",
                    key=f"source_stale:{source.source_id}",
                    status="weakened",
                    materiality="unknown",
                    before={"age_days": old_age} if old_age is not None else None,
                    after={"age_days": age_days, "threshold_days": stale_after_days},
                    before_evidence=[old.source_id] if old else [],
                    after_evidence=[source.source_id],
                    method="deterministic_source_freshness_threshold",
                    explanation=(
                        f"Source {source.source_id} exceeded the configured "
                        f"{stale_after_days}-day freshness threshold."
                    ),
                    confidence=1.0,
                )
            )

    previous_conflicts = _source_conflicts(previous)
    for fact_key, sources in _source_conflicts(current).items():
        evidence = sorted(source.source_id for source in sources)
        changes.append(
            _change(
                ticker=current.ticker,
                category="evidence",
                key=f"source_conflict:{fact_key}",
                status=("persistent" if fact_key in previous_conflicts else "new"),
                materiality="unknown",
                before=(
                    _conflict_values(previous_conflicts[fact_key])
                    if fact_key in previous_conflicts
                    else None
                ),
                after=_conflict_values(sources),
                before_evidence=(
                    sorted(item.source_id for item in previous_conflicts[fact_key])
                    if fact_key in previous_conflicts
                    else []
                ),
                after_evidence=evidence,
                method="deterministic_source_value_conflict",
                explanation=f"Sources disagree on normalized fact {fact_key}.",
                confidence=1.0,
            )
        )
    return changes


def _source_conflicts(
    snapshot: CompanyResearchSnapshot,
) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for source in snapshot.sources:
        fact_key = source.metadata.get("fact_key")
        if isinstance(fact_key, str) and "value" in source.metadata:
            grouped.setdefault(fact_key, []).append(source)
    return {
        key: sources
        for key, sources in grouped.items()
        if len(
            {
                json.dumps(source.metadata["value"], sort_keys=True)
                for source in sources
            }
        )
        > 1
    }


def _conflict_values(sources: list[Any]) -> dict[str, Any]:
    return {
        source.source_id: source.metadata["value"]
        for source in sorted(sources, key=lambda item: item.source_id)
    }


def _comparison_warnings(
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
) -> list[str]:
    warnings: list[str] = []
    previous_states = {item.component: item.state for item in previous.components}
    for component in current.components:
        if (
            component.state in {"failed", "unavailable"}
            and previous_states.get(component.component) in {"complete", "partial"}
        ):
            warnings.append(
                f"component_not_comparable:{component.component}:{component.state}"
            )
    return warnings


def _latest_financial_points(
    points: list[FinancialMetricPoint],
) -> dict[tuple[str, str], FinancialMetricPoint]:
    latest: dict[tuple[str, str], FinancialMetricPoint] = {}
    for point in points:
        if point.period_kind not in {"quarter", "annual", "ttm"}:
            continue
        key = (point.metric, point.period_kind)
        existing = latest.get(key)
        if existing is None or (point.period_end, point.filed_at or point.period_end) > (
            existing.period_end,
            existing.filed_at or existing.period_end,
        ):
            latest[key] = point
    return latest


def _financial_evidence(point: FinancialMetricPoint) -> list[str]:
    return sorted(set(point.source_accession_numbers or ([point.accession_number] if point.accession_number else [])))


def _point_value(point: FinancialMetricPoint) -> dict[str, Any]:
    return {
        "value": point.value,
        "unit": point.unit,
        "period_end": point.period_end.isoformat(),
        "period_kind": point.period_kind,
    }


def _numeric_materiality(percent: float | None) -> Materiality:
    if percent is None:
        return "unknown"
    magnitude = abs(percent)
    if magnitude >= 0.1:
        return "high"
    if magnitude >= 0.05:
        return "medium"
    return "low"


def _evidence_safe_materiality(
    materiality: Materiality,
    before_evidence: list[str],
    after_evidence: list[str],
) -> Materiality:
    if materiality == "high" and (not before_evidence or not after_evidence):
        return "unknown"
    return materiality


def _change(
    *,
    ticker: str,
    category: ChangeCategory,
    key: str,
    status: ChangeStatus,
    materiality: Materiality,
    before: Any,
    after: Any,
    before_evidence: list[str],
    after_evidence: list[str],
    method: str,
    explanation: str,
    confidence: float,
) -> ResearchChange:
    identity = json.dumps(
        {
            "ticker": ticker,
            "category": category,
            "key": key,
            "status": status,
            "before": before,
            "after": after,
            "before_evidence": before_evidence,
            "after_evidence": after_evidence,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return ResearchChange(
        change_id=f"change-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        ticker=ticker,
        category=category,
        key=key,
        status=status,
        materiality=materiality,
        before=before,
        after=after,
        before_evidence_ids=before_evidence,
        after_evidence_ids=after_evidence,
        detection_method=method,
        explanation=explanation,
        confidence=confidence,
    )


def _component_comparable(
    snapshot: CompanyResearchSnapshot,
    component: str,
) -> bool:
    states = [
        item.state for item in snapshot.components if item.component == component
    ]
    return not states or all(state in {"complete", "partial"} for state in states)


__all__ = [
    "ChangeReviewRequest",
    "ResearchChange",
    "ResearchChangeSet",
    "detect_research_changes",
]
