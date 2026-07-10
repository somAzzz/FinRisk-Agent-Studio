"""Conservative mappings from disclosed risks to financial value drivers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FinancialDriver = Literal[
    "volume",
    "price",
    "cost",
    "margin",
    "capital_expenditure",
    "working_capital",
    "financing",
]
ImpactDirection = Literal["adverse", "favorable", "mixed", "unknown"]


class RiskFinancialImpact(BaseModel):
    """An evidence-linked, deliberately unquantified financial impact path."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    affected_segment: str | None = None
    drivers: list[FinancialDriver] = Field(default_factory=list)
    affected_metrics: list[str] = Field(default_factory=list)
    direction: ImpactDirection = "unknown"
    time_horizon: str = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    quantification_status: Literal["unquantified", "quantified"] = "unquantified"
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_impact: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    rationale: str


_TYPE_MAP: dict[str, tuple[list[FinancialDriver], list[str]]] = {
    "macro": (["volume", "price", "cost"], ["revenue", "gross_margin"]),
    "policy": (["price", "cost", "capital_expenditure"], ["revenue", "free_cash_flow"]),
    "climate": (["cost", "capital_expenditure"], ["operating_margin", "free_cash_flow"]),
    "supply_chain": (["volume", "cost", "working_capital"], ["revenue", "gross_margin", "free_cash_flow"]),
    "competition": (["volume", "price", "margin"], ["revenue", "gross_margin", "operating_margin"]),
    "regulatory": (["cost", "capital_expenditure"], ["operating_margin", "free_cash_flow"]),
    "technology": (["volume", "capital_expenditure", "margin"], ["revenue", "operating_margin", "free_cash_flow"]),
    "geopolitical": (["volume", "cost", "working_capital"], ["revenue", "gross_margin", "free_cash_flow"]),
    "financial": (["financing", "working_capital"], ["net_income", "free_cash_flow", "total_debt"]),
    "operational": (["volume", "cost", "margin"], ["revenue", "operating_margin", "free_cash_flow"]),
}


def map_risk_financial_impact(
    risk: Any,
    *,
    evidence_ids: list[str],
    time_horizon: str,
) -> RiskFinancialImpact:
    """Map one risk to possible value drivers without inventing magnitudes."""
    risk_type = str(getattr(risk, "risk_type", ""))
    drivers, metrics = _TYPE_MAP.get(risk_type, ([], []))
    drivers = list(drivers)
    metrics = list(metrics)
    text = " ".join(
        [
            str(getattr(risk, "risk_factor", "")),
            str(getattr(risk, "evidence_quote", "")),
        ]
    ).lower()
    if any(term in text for term in ("demand", "customer", "sales", "orders")):
        _append_unique(drivers, "volume")
        _append_unique(metrics, "revenue")
    if any(term in text for term in ("cost", "inflation", "component", "input")):
        _append_unique(drivers, "cost")
        _append_unique(metrics, "gross_margin")
    if any(term in text for term in ("inventory", "receivable", "working capital")):
        _append_unique(drivers, "working_capital")
        _append_unique(metrics, "free_cash_flow")
    if any(term in text for term in ("interest rate", "debt", "liquidity")):
        _append_unique(drivers, "financing")
        _append_unique(metrics, "net_income")

    confidence = float(getattr(risk, "confidence", 0.0) or 0.0)
    return RiskFinancialImpact(
        risk_id=str(getattr(risk, "risk_id", "")),
        drivers=drivers,
        affected_metrics=metrics,
        direction="adverse" if drivers else "unknown",
        time_horizon=time_horizon,
        evidence_ids=evidence_ids,
        evidence_quote=str(getattr(risk, "evidence_quote", "")),
        confidence=min(confidence, 0.75),
        assumptions=[
            "No probability or financial magnitude has been inferred.",
            "Quantification requires segment exposure and scenario inputs.",
        ],
        rationale=(
            f"{risk_type or 'unclassified'} risk mapped to common financial "
            "transmission channels; analyst validation required."
        ),
    )


def _append_unique(values: list, value: str) -> None:
    if value not in values:
        values.append(value)


__all__ = ["RiskFinancialImpact", "map_risk_financial_impact"]
