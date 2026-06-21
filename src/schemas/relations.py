"""Relation model: typed edges between entities, backed by evidence."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.entities import Entity
from src.schemas.evidence import Evidence

RelationType = Literal[
    "supplies_to",
    "buys_from",
    "customer_of",
    "competitor_of",
    "has_segment",
    "sells_product",
    "depends_on",
    "exposed_to",
    "mentions_risk",
    "impacted_by",
    "benefits_from",
    "subsidiary_of",
    "supports_claim",
]


class Relation(BaseModel):
    """A directed or undirected edge between two entities."""

    model_config = ConfigDict(extra="forbid")

    relation_id: str
    source: Entity
    target: Entity
    relation_type: RelationType
    direction: Literal["directed", "undirected"] = "directed"
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
