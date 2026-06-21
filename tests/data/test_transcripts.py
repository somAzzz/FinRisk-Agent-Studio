"""Tests for :mod:`src.data.transcripts`.

Covers the role/section heuristics, the on-disk cache round-trip, and the
transcript provider exception hierarchy. The tests use a temporary
``cache_dir`` so they do not touch the real ``.cache/fintext_llm`` directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.data.transcripts import (
    TranscriptCache,
    TranscriptMeta,
    TranscriptNotFoundError,
    TranscriptProvider,
    TranscriptProviderConfigError,
    TranscriptProviderError,
    TranscriptRateLimitError,
    infer_role,
    infer_section,
)
from src.schemas.transcripts import Transcript, TranscriptTurn


# --- infer_role ----------------------------------------------------------


def test_infer_role_detects_ceo_by_title() -> None:
    """The full CEO title and the CEO acronym both map to ``ceo``."""
    assert infer_role("Tim Cook, Chief Executive Officer") == "ceo"
    assert infer_role("Jane Doe (CEO)") == "ceo"


def test_infer_role_detects_cfo_by_title() -> None:
    """The full CFO title and the CFO acronym both map to ``cfo``."""
    assert infer_role("Luca Maestri, Chief Financial Officer") == "cfo"
    assert infer_role("John Smith - CFO") == "cfo"


def test_infer_role_detects_analyst() -> None:
    """Speakers tagged as analysts map to ``analyst``."""
    assert infer_role("Katy Huberty, Analyst - Morgan Stanley") == "analyst"
    assert infer_role("Analyst") == "analyst"


def test_infer_role_detects_operator() -> None:
    """The literal 'Operator' maps to ``operator``."""
    assert infer_role("Operator") == "operator"


def test_infer_role_falls_back_to_unknown() -> None:
    """Unrecognized speakers map to ``unknown``."""
    assert infer_role("Conference Attendee") == "unknown"
    assert infer_role("") == "unknown"


# --- infer_section -------------------------------------------------------


def test_infer_section_prepared_remarks_before_marker() -> None:
    """Before the Q&A marker the section is ``prepared_remarks``."""
    assert infer_section("Welcome to our call.", "unknown") == "prepared_remarks"


def test_infer_section_flips_to_qa_after_marker() -> None:
    """Once the Q&A marker appears, the section is ``qa`` and stays there."""
    marker = "We will now begin the Question-and-Answer Session."
    assert infer_section(marker, "prepared_remarks") == "qa"
    # Subsequent turns remain in qa even without further markers.
    assert infer_section("My question is about margins.", "qa") == "qa"


def test_infer_section_unknown_when_no_context() -> None:
    """An empty context and empty text returns ``unknown``."""
    assert infer_section("", "unknown") == "unknown"


# --- TranscriptMeta ------------------------------------------------------


def test_transcript_meta_rejects_extra_fields() -> None:
    """``TranscriptMeta`` uses ``extra='forbid'`` per the plan."""
    meta = TranscriptMeta(
        ticker="AAPL",
        year=2024,
        quarter=1,
        provider="alpha_vantage",
    )
    with pytest.raises(ValueError):
        TranscriptMeta.model_validate(
            {
                "ticker": "AAPL",
                "year": 2024,
                "quarter": 1,
                "provider": "alpha_vantage",
                "unknown": "field",
            }
        )
    assert meta.ticker == "AAPL"


def test_transcript_provider_is_a_protocol() -> None:
    """The :class:`TranscriptProvider` is exposed as a Protocol class."""
    # Structural: it must expose the expected attributes on the class.
    assert hasattr(TranscriptProvider, "provider_name")
    assert hasattr(TranscriptProvider, "list_transcripts")
    assert hasattr(TranscriptProvider, "get_transcript")


# --- Exception hierarchy -------------------------------------------------


def test_exception_hierarchy() -> None:
    """All provider exceptions derive from :class:`TranscriptProviderError`."""
    assert issubclass(TranscriptProviderConfigError, TranscriptProviderError)
    assert issubclass(TranscriptRateLimitError, TranscriptProviderError)
    assert issubclass(TranscriptNotFoundError, TranscriptProviderError)
    assert issubclass(TranscriptProviderError, Exception)

    # Instances can be raised and caught as the base class.
    with pytest.raises(TranscriptProviderError):
        raise TranscriptProviderConfigError("no key")
    with pytest.raises(TranscriptProviderError):
        raise TranscriptRateLimitError("429")
    with pytest.raises(TranscriptProviderError):
        raise TranscriptNotFoundError("missing")


# --- TranscriptCache -----------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    """Ensure each test sees a fresh ``Settings`` instance.

    The :func:`src.config.get_settings` helper is ``lru_cache``-memoized for
    production use, but tests rely on monkeypatched env vars, so we have to
    flush the cache before each test.
    """
    from src.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_transcript(ticker: str, year: int, quarter: int) -> Transcript:
    """Build a tiny :class:`Transcript` used in cache tests."""
    return Transcript(
        ticker=ticker,
        year=year,
        quarter=quarter,
        provider="alpha_vantage",
        transcript_id=f"{ticker}-{year}Q{quarter}",
        published_at=datetime(2024, 1, 30, 21, 0, 0),
        turns=[
            TranscriptTurn(
                speaker="Tim Cook",
                role="ceo",
                text="Welcome.",
                section="prepared_remarks",
                turn_index=0,
            )
        ],
    )


def test_transcript_cache_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache writes and reads back the same :class:`Transcript`."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    cache = TranscriptCache()
    transcript = _make_transcript("AAPL", 2024, 1)

    assert cache.get("alpha_vantage", "AAPL", 2024, 1) is None
    cache.set(transcript)

    cached = cache.get("alpha_vantage", "AAPL", 2024, 1)
    assert cached is not None
    assert cached.ticker == "AAPL"
    assert cached.year == 2024
    assert cached.quarter == 1
    assert cached.provider == "alpha_vantage"
    assert cached.transcript_id == transcript.transcript_id
    assert len(cached.turns) == 1
    assert cached.turns[0].role == "ceo"


def test_transcript_cache_path_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache files are stored under ``<cache_dir>/transcripts/<provider>/...``."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    cache = TranscriptCache()
    cache.set(_make_transcript("aapl", 2024, 2))

    expected = (
        tmp_path
        / "transcripts"
        / "alpha_vantage"
        / "AAPL"
        / "2024Q2.json"
    )
    assert expected.is_file()


def test_transcript_cache_handles_corrupt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt cache file is treated as a miss rather than raising."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    cache = TranscriptCache()
    path = (
        tmp_path
        / "transcripts"
        / "alpha_vantage"
        / "AAPL"
        / "2024Q1.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert cache.get("alpha_vantage", "AAPL", 2024, 1) is None
