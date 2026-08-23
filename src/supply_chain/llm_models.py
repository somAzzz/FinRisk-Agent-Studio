"""Typed outputs for supply-chain analysis Agents."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupplyChainRequirementType = Literal[
    "component",
    "service",
    "infrastructure",
    "energy",
    "commodity",
    "region",
    "unknown",
]


class RequirementItem(BaseModel):
    """One validated upstream product requirement."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    node_type: SupplyChainRequirementType = "unknown"
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=240)

    @field_validator("label", "reason", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()


class RequirementDecomposition(BaseModel):
    """Validated batch returned by the requirement decomposition Agent."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[RequirementItem] = Field(default_factory=list, max_length=10)


class SupplierProposal(BaseModel):
    """One hypothesis linking a requirement to a supplier candidate."""

    model_config = ConfigDict(extra="forbid")

    requirement_node_id: str = Field(default="", max_length=180)
    requirement_label: str = Field(default="", max_length=120)
    supplier_name: str = Field(min_length=1, max_length=120)
    ticker: str | None = Field(default=None, max_length=16)
    product_or_service: str = Field(default="", max_length=160)
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    uncertainty: str = Field(default="", max_length=240)

    @field_validator(
        "requirement_node_id",
        "requirement_label",
        "supplier_name",
        "product_or_service",
        "uncertainty",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalise_ticker(cls, value: Any) -> str | None:
        ticker = str(value or "").strip().upper()
        if not ticker or ticker in {"N/A", "NA", "NONE", "NULL"}:
            return None
        return ticker


class SupplierProposalBatch(BaseModel):
    """Validated supplier hypotheses returned by the proposal Agent."""

    model_config = ConfigDict(extra="forbid")

    suppliers: list[SupplierProposal] = Field(default_factory=list, max_length=100)


class NodeIntelligenceProfile(BaseModel):
    """One validated intelligence card for a supply-chain graph node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=800)
    key_items: list[str] = Field(default_factory=list, max_length=6)
    applications: list[str] = Field(default_factory=list, max_length=6)
    risk_factors: list[str] = Field(default_factory=list, max_length=6)
    comparable_entities: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    @field_validator("node_id", "summary", mode="before")
    @classmethod
    def _strip_required_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "key_items",
        "applications",
        "risk_factors",
        "comparable_entities",
        mode="before",
    )
    @classmethod
    def _normalise_text_list(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:100] for item in value if str(item).strip()]


class NodeProfileBatch(BaseModel):
    """Validated node cards returned by the profiling Agent."""

    model_config = ConfigDict(extra="forbid")

    profiles: list[NodeIntelligenceProfile] = Field(default_factory=list, max_length=14)


__all__ = [
    "NodeIntelligenceProfile",
    "NodeProfileBatch",
    "RequirementDecomposition",
    "RequirementItem",
    "SupplierProposal",
    "SupplierProposalBatch",
]
