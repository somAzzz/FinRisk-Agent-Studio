"""Adapters from structured FinRisk reports to immutable risk observations."""

from __future__ import annotations

from typing import Any

from src.research.models import RiskObservation


def risk_observations_from_report(report: Any | None) -> list[RiskObservation]:
    if report is None:
        return []
    top_risks = getattr(report, "top_risks", None)
    if top_risks is None and isinstance(report, dict):
        top_risks = report.get("top_risks")
    observations: list[RiskObservation] = []
    for item in top_risks or []:
        value = item if isinstance(item, dict) else item.model_dump(mode="json")
        lifecycle = str(value.get("lifecycle") or "unknown")
        status = {
            "emerging": "new",
            "current": "persistent",
            "receding": "weakened",
        }.get(lifecycle, "unknown")
        observations.append(
            RiskObservation(
                risk_id=str(value.get("risk_id") or ""),
                title=str(value.get("title") or value.get("summary") or "Risk"),
                status=status,
                severity=str(value.get("severity")) if value.get("severity") else None,
                evidence_ids=[str(item) for item in value.get("supporting_evidence_ids", [])],
                attributes={
                    "risk_type": value.get("risk_type"),
                    "final_score": value.get("final_score"),
                    "lifecycle": lifecycle,
                    "summary": value.get("summary"),
                },
            )
        )
    return [item for item in observations if item.risk_id]


__all__ = ["risk_observations_from_report"]
