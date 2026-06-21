"""Tests for :class:`FMPProvider`.

HTTP access is faked by monkeypatching ``requests.Session.get`` at the class
level so the tests never touch the public FMP API.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.data.providers.fmp import FMPProvider
from src.data.transcripts import (
    TranscriptCache,
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
    TranscriptRateLimitError,
    infer_role,
    infer_section,
)
from src.schemas.transcripts import Transcript


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(
        self,
        status_code: int = 200,
        json_payload: Any | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_payload if json_payload is not None else {}
        self.url = "https://financialmodelingprep.com/api/v3/..."

    def json(self) -> Any:
        return self._json


def _patch_session_get(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    captured: dict[str, Any],
) -> None:
    """Replace ``requests.Session.get`` with a capturing stub."""

    def fake_get(
        self: Any, *args: Any, **kwargs: Any
    ) -> FakeResponse:  # noqa: ARG001
        captured.setdefault("calls", 0)
        captured["calls"] += 1
        captured["args"] = args
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr(
        "requests.Session.get", fake_get, raising=True
    )


# --- Configuration -------------------------------------------------------


def test_missing_api_key_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructor raises :class:`TranscriptProviderConfigError` without a key."""
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(TranscriptProviderConfigError):
        FMPProvider()


def test_api_key_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``FMP_API_KEY`` env var is used when no explicit key is passed."""
    monkeypatch.setenv("FMP_API_KEY", "env-key")
    provider = FMPProvider()
    assert provider.api_key == "env-key"


# --- list_transcripts ----------------------------------------------------


def _list_payload() -> list[dict[str, Any]]:
    """Build a representative FMP list endpoint payload."""
    return [
        {
            "id": 1001,
            "symbol": "AAPL",
            "year": 2024,
            "quarter": 1,
            "date": "2024-02-01 21:30:00",
            "title": "Apple Q1 2024 Earnings Call",
            "url": "https://financialmodelingprep.com/...",
        },
        {
            "id": 1010,
            "symbol": "AAPL",
            "year": 2023,
            "quarter": 4,
            "date": "2023-11-02 21:30:00",
            "title": "Apple Q4 2023 Earnings Call",
            "url": "https://financialmodelingprep.com/...",
        },
    ]


def test_list_transcripts_parses_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The list endpoint is mapped to a list of :class:`TranscriptMeta`."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _list_payload()), captured
    )
    provider = FMPProvider(api_key="key")
    metas = provider.list_transcripts("AAPL")

    assert len(metas) == 2
    assert metas[0].ticker == "AAPL"
    assert metas[0].year == 2024
    assert metas[0].quarter == 1
    assert metas[0].provider == "fmp"
    assert metas[0].title == "Apple Q1 2024 Earnings Call"
    assert metas[0].transcript_id == "1001"
    assert metas[0].published_at is not None

    kwargs = captured["kwargs"]
    assert kwargs["params"]["symbol"] == "AAPL"
    assert kwargs["params"]["apikey"] == "key"


def test_list_transcripts_returns_empty_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty list payload returns an empty list of metas."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, []), captured)
    provider = FMPProvider(api_key="key")
    assert provider.list_transcripts("AAPL") == []


# --- get_transcript ------------------------------------------------------


def _detail_payload() -> list[dict[str, Any]]:
    """Build a representative FMP detail endpoint payload."""
    return [
        {
            "id": 2002,
            "symbol": "AAPL",
            "year": 2024,
            "quarter": 1,
            "date": "2024-02-01 21:30:00",
            "title": "Apple Q1 2024 Earnings Call",
            "url": "https://financialmodelingprep.com/...",
            "content": "\n".join(
                [
                    "Tim Cook: Welcome to our Q1 2024 earnings call.",
                    "Luca Maestri: Revenue was a record $119.6 billion.",
                    "Operator: We will now begin the Question-and-Answer Session.",
                    "Katy Huberty, Analyst - Morgan Stanley: "
                    "Can you discuss iPhone demand?",
                    "Tim Cook: We saw strong demand across emerging markets.",
                ]
            ),
        },
        {
            "id": 1999,
            "symbol": "AAPL",
            "year": 2023,
            "quarter": 4,
            "date": "2023-11-02 21:30:00",
            "content": "old transcript",
        },
    ]


def test_get_transcript_parses_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid detail payload is parsed into a :class:`Transcript`."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _detail_payload()), captured
    )
    provider = FMPProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    assert isinstance(transcript, Transcript)
    assert transcript.ticker == "AAPL"
    assert transcript.year == 2024
    assert transcript.quarter == 1
    assert transcript.provider == "fmp"
    assert transcript.transcript_id == "2002"
    assert transcript.title == "Apple Q1 2024 Earnings Call"
    assert len(transcript.turns) == 5
    assert captured["kwargs"]["params"]["year"] == 2024
    assert captured["kwargs"]["params"]["quarter"] == 1
    assert captured["kwargs"]["params"]["apikey"] == "key"


def test_get_transcript_section_flips_to_qa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turns after the Q&A marker carry ``section='qa'``."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _detail_payload()), captured
    )
    provider = FMPProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    sections = [t.section for t in transcript.turns]
    assert sections[0] == "prepared_remarks"
    assert sections[1] == "prepared_remarks"
    assert sections[2] == "qa"
    assert sections[3] == "qa"
    assert sections[4] == "qa"


def test_get_transcript_role_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Speakers in the FMP detail payload get the right inferred role."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _detail_payload()), captured
    )
    provider = FMPProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    roles = [t.role for t in transcript.turns]
    assert roles[0] == "ceo"
    assert roles[1] == "cfo"
    assert roles[2] == "operator"
    assert roles[3] == "analyst"
    assert roles[4] == "ceo"


def test_get_transcript_returns_not_found_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A payload that lacks the period raises TranscriptNotFoundError."""
    captured: dict[str, Any] = {}
    # Detail payload only contains 2024 Q1; we request Q2.
    _patch_session_get(
        monkeypatch, FakeResponse(200, _detail_payload()), captured
    )
    provider = FMPProvider(api_key="key")
    with pytest.raises(TranscriptNotFoundError):
        provider.get_transcript("AAPL", 2024, 2)


# --- HTTP error mapping --------------------------------------------------


def test_http_404_maps_to_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 response raises :class:`TranscriptNotFoundError`."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(404, {}), captured)
    provider = FMPProvider(api_key="key")
    with pytest.raises(TranscriptNotFoundError):
        provider.get_transcript("AAPL", 2024, 1)


def test_http_429_maps_to_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 429 response raises :class:`TranscriptRateLimitError`."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(429, {}), captured)
    provider = FMPProvider(api_key="key")
    with pytest.raises(TranscriptRateLimitError):
        provider.get_transcript("AAPL", 2024, 1)


# --- Caching -------------------------------------------------------------


def test_cache_hit_avoids_http_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A pre-populated cache short-circuits the HTTP request entirely."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    cache = TranscriptCache()
    provider = FMPProvider(api_key="key", cache=cache)

    # Seed the cache by manually constructing a transcript using the same
    # parser the provider uses.
    payload = _detail_payload()
    match = provider._first_match(payload, 2024, 1)
    assert match is not None
    transcript = provider._parse_detail(match, "AAPL", 2024, 1)
    cache.set(transcript)

    captured: dict[str, Any] = {}

    def boom(
        self: Any, *args: Any, **kwargs: Any
    ) -> FakeResponse:  # noqa: ARG001
        captured["called"] = True
        raise AssertionError("HTTP should not be called on cache hit")

    monkeypatch.setattr("requests.Session.get", boom, raising=True)

    result = provider.get_transcript("AAPL", 2024, 1)
    assert result.ticker == "AAPL"
    assert captured == {}


# --- Re-exported helpers -------------------------------------------------


def test_infer_section_helper_accessible() -> None:
    """infer_section and infer_role are usable from the data package."""
    assert infer_role("CEO Jane") == "ceo"
    assert (
        infer_section(
            "We will now begin the Question-and-Answer Session.",
            "unknown",
        )
        == "qa"
    )
