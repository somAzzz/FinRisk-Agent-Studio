"""Entity model: canonical representation of a business entity."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.evidence import Evidence

EntityType = Literal[
    "company",
    "product",
    "segment",
    "customer",
    "supplier",
    "competitor",
    "country",
    "region",
    "commodity",
    "policy",
    "risk",
    "opportunity",
    "executive",
    "event",
]


class Entity(BaseModel):
    """A normalized business entity referenced by the knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    name: str
    entity_type: EntityType
    normalized_name: str
    ticker: str | None = None
    cik: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
