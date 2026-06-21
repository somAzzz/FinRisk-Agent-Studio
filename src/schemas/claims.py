"""Claim model: the project-wide assertion primitive."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation

ClaimType = Literal[
    "risk",
    "opportunity",
    "sentiment",
    "policy_exposure",
    "geopolitical_exposure",
    "supply_chain",
    "financial_signal",
]


class Claim(BaseModel):
    """An evidence-backed assertion made by the extraction pipeline."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_type: ClaimType
    statement: str
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    counter_evidence: list[Evidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
