"""Transcript provider abstractions and parsing utilities.

Defines a common :class:`TranscriptProvider` protocol, exceptions raised by
implementations, a simple JSON file cache, and helpers for normalizing
provider-specific speaker turns into the shared :class:`Transcript` schema
defined in :mod:`src.schemas.transcripts`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from src.config import get_settings
from src.schemas.transcripts import Transcript, TranscriptTurn

Role = Literal["ceo", "cfo", "executive", "analyst", "operator", "unknown"]
Section = Literal["prepared_remarks", "qa", "unknown"]


class TranscriptProviderError(Exception):
    """Base class for all errors raised by transcript providers."""


class TranscriptProviderConfigError(TranscriptProviderError):
    """Raised when a provider is missing required configuration (e.g. API key)."""


class TranscriptRateLimitError(TranscriptProviderError):
    """Raised when an upstream transcript API signals rate limiting."""


class TranscriptNotFoundError(TranscriptProviderError):
    """Raised when a requested transcript is unavailable from the provider."""


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


class TranscriptProvider(Protocol):
    """Protocol implemented by every transcript provider.

    Subclasses must set ``provider_name`` as a class attribute. The default
    empty string keeps ``hasattr(provider, "provider_name")`` truthful.
    """

    provider_name: str = ""

    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        """Return a list of available transcripts for ``ticker``."""
        ...

    def get_transcript(self, ticker: str, year: int, quarter: int) -> Transcript:
        """Return the full :class:`Transcript` for the given ticker/period."""
        ...


_QA_MARKER_RE = re.compile(
    r"question[- ]and[- ]answer\s+session", re.IGNORECASE
)


def infer_role(speaker: str) -> Role:
    """Infer a normalized role for ``speaker``.

    Matching is case-insensitive and uses the same rules described in the
    implementation plan. Speakers explicitly identified as CEO or CFO are
    mapped to ``"ceo"`` / ``"cfo"``; analysts and the call operator are
    recognized; anything else falls through to ``"unknown"``.
    """
    text = (speaker or "").lower()
    if not text:
        return "unknown"
    if "operator" in text:
        return "operator"
    if "analyst" in text:
        return "analyst"
    if "chief executive officer" in text or "ceo" in text:
        return "ceo"
    if "chief financial officer" in text or "cfo" in text:
        return "cfo"
    return "unknown"


def infer_section(text: str, current_section: str) -> Section:
    """Update the section label using a heuristic on ``text``.

    Once the transcript crosses the "Question-and-Answer Session" marker it
    stays in ``"qa"``; prior to that the section is ``"prepared_remarks"``.
    When neither rule applies and the caller hasn't yet inferred a section
    (``current_section == "unknown"`` with no marker in ``text``), the helper
    returns ``"unknown"`` so callers can opt out of labeling ambiguous text.
    """
    if _QA_MARKER_RE.search(text or ""):
        return "qa"
    if current_section == "qa":
        return "qa"
    if current_section == "unknown" and not (text or "").strip():
        return "unknown"
    return "prepared_remarks"


class TranscriptCache:
    """File-based JSON cache for :class:`Transcript` objects.

    Files are stored under ``<cache_dir>/transcripts/<provider>/<ticker>/
    <year>Q<quarter>.json`` so each period is keyed deterministically.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        settings = get_settings()
        base = cache_dir if cache_dir is not None else settings.cache_dir
        self.root: Path = Path(base) / "transcripts"

    def _path(self, provider: str, ticker: str, year: int, quarter: int) -> Path:
        safe_ticker = ticker.upper()
        return self.root / provider / safe_ticker / f"{year}Q{quarter}.json"

    def get(
        self, provider: str, ticker: str, year: int, quarter: int
    ) -> Transcript | None:
        """Return the cached transcript, or ``None`` if not present/invalid."""
        path = self._path(provider, ticker, year, quarter)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return Transcript.model_validate(payload)
        except Exception:
            return None

    def set(self, transcript: Transcript) -> Path:
        """Persist ``transcript`` to disk and return the path written."""
        path = self._path(
            transcript.provider,
            transcript.ticker,
            transcript.year,
            transcript.quarter,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            transcript.model_dump_json(indent=2), encoding="utf-8"
        )
        return path


__all__ = [
    "Section",
    "Transcript",
    "TranscriptCache",
    "TranscriptMeta",
    "TranscriptNotFoundError",
    "TranscriptProvider",
    "TranscriptProviderConfigError",
    "TranscriptProviderError",
    "TranscriptRateLimitError",
    "TranscriptTurn",
    "infer_role",
    "infer_section",
]
