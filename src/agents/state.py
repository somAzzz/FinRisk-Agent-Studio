"""Runtime state containers shared across agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation


class ToolCall(BaseModel):
    """A single recorded invocation of a tool during a runtime step."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any]
    result_summary: str | None = None
    success: bool = True
    created_at: datetime


class AgentState(BaseModel):
    """Mutable, JSON-serializable state passed between agents during a run."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    ticker: str | None = None
    company_name: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tool_history: list[ToolCall] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    max_steps: int = 10
    current_step: int = 0
