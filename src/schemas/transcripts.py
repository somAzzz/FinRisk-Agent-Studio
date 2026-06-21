"""Transcript model: earnings-call and other corporate call transcripts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TranscriptTurn(BaseModel):
    """One speaker turn inside a transcript."""

    model_config = ConfigDict(extra="forbid")

    speaker: str
    role: Literal["ceo", "cfo", "executive", "analyst", "operator", "unknown"]
    text: str
    section: Literal["prepared_remarks", "qa", "unknown"]
    turn_index: int


class Transcript(BaseModel):
    """A full earnings-call transcript."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    year: int
    quarter: int
    provider: str
    transcript_id: str
    title: str | None = None
    published_at: datetime | None = None
    turns: list[TranscriptTurn]
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptMeta(BaseModel):
    """Lightweight metadata describing a single transcript entry."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    year: int
    quarter: int
    provider: str
    title: str | None = None
    published_at: datetime | None = None
    transcript_id: str | None = None
    url: str | None = None
