"""FilingRecord: canonical wrapper for SEC / Hugging Face filings."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FilingRecord(BaseModel):
    """A single filing row, agnostic to its ingestion source."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["huggingface", "sec"]
    cik: str
    ticker: str | None = None
    company_name: str | None = None
    form_type: str = "10-K"
    year: int | None = None
    filing_date: date | None = None
    accession_number: str | None = None
    sections: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilingMetadata(BaseModel):
    """Metadata describing a single SEC filing discovered via the submissions API."""

    model_config = ConfigDict(extra="forbid")

    cik: str
    accession_number: str
    form_type: str
    filing_date: date
    report_date: date | None = None
    primary_document: str
    url: str
