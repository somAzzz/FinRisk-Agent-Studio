"""Evidence model: the canonical provenance record for the project."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal[
    "edgar_corpus",
    "sec_filing",
    "sec_xbrl",
    "transcript",
    "web",
    "browser",
    "manual",
]


class Evidence(BaseModel):
    """A piece of provenance attached to extracted facts or claims."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: SourceType
    source_id: str
    title: str | None = None
    url: str | None = None
    section: str | None = None
    speaker: str | None = None
    quote: str
    retrieved_at: datetime
    published_at: datetime | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quote")
    @classmethod
    def _quote_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            msg = "Evidence.quote must be a non-empty string."
            raise ValueError(msg)
        return value
