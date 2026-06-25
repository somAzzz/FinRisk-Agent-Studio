"""Tests for :class:`AlphaVantageProvider`.

Network access is faked by monkeypatching ``requests.Session.get`` at the
class level. The provider exposes ``session`` so tests can drive the same
instance used in production code.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.data.providers.alpha_vantage import AlphaVantageProvider
from src.data.transcripts import (
    TranscriptCache,
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
    TranscriptRateLimitError,
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
        self.url = "https://www.alphavantage.co/query"

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
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    with pytest.raises(TranscriptProviderConfigError):
        AlphaVantageProvider()


def test_explicit_api_key_bypasses_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``api_key`` is used even when the env var is unset."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    provider = AlphaVantageProvider(api_key="explicit-key")
    assert provider.api_key == "explicit-key"


def test_api_key_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env var ``ALPHA_VANTAGE_API_KEY`` is used when no key is passed."""
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "env-key")
    provider = AlphaVantageProvider()
    assert provider.api_key == "env-key"


# --- list_transcripts ----------------------------------------------------


def test_list_transcripts_returns_empty() -> None:
    """Alpha Vantage has no list endpoint; the provider returns ``[]``."""
    provider = AlphaVantageProvider(api_key="key")
    assert provider.list_transcripts("AAPL") == []


# --- Error mapping -------------------------------------------------------


def test_get_transcript_rate_limit_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An Alpha Vantage ``Note`` about call frequency raises rate limit."""
    captured: dict[str, Any] = {}
    payload = {
        "Note": (
            "Thank you for using Alpha Vantage! "
            "Our standard API rate limit is 25 requests per day."
        )
    }
    _patch_session_get(
        monkeypatch,
        FakeResponse(200, payload),
        captured,
    )
    provider = AlphaVantageProvider(api_key="key")
    with pytest.raises(TranscriptRateLimitError):
        provider.get_transcript("AAPL", 2024, 1)


def test_get_transcript_information_field_raises_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ``Information`` field (premium-only) also maps to rate limit."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch,
        FakeResponse(200, {"Information": "Premium endpoint - upgrade required"}),
        captured,
    )
    provider = AlphaVantageProvider(api_key="key")
    with pytest.raises(TranscriptRateLimitError):
        provider.get_transcript("AAPL", 2024, 1)


def test_get_transcript_not_found_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response whose note indicates a missing transcript raises not-found."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch,
        FakeResponse(200, {"Note": "Transcript not found for AAPL 2024Q1"}),
        captured,
    )
    provider = AlphaVantageProvider(api_key="key")
    with pytest.raises(TranscriptNotFoundError):
        provider.get_transcript("AAPL", 2024, 1)


def test_get_transcript_empty_payload_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ``transcript`` array is treated as 'not found'."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch,
        FakeResponse(200, {"transcript": []}),
        captured,
    )
    provider = AlphaVantageProvider(api_key="key")
    with pytest.raises(TranscriptNotFoundError):
        provider.get_transcript("AAPL", 2024, 1)


# --- Happy path parsing --------------------------------------------------


def _build_payload() -> dict[str, Any]:
    """Build a representative Alpha Vantage transcript payload."""
    return {
        "symbol": "AAPL",
        "transcript_id": "abc-123",
        "title": "Apple Q1 2024 Earnings Call",
        "url": "https://www.alphavantage.co/transcript/abc-123",
        "transcript": [
            {
                "speaker": "Tim Cook",
                "text": "Welcome to Apple Q1 2024 earnings call.",
            },
            {
                "speaker": "Luca Maestri",
                "text": "Revenue was a record $119.6 billion.",
            },
            {
                "speaker": "Operator",
                "text": "We will now begin the Question-and-Answer Session.",
            },
            {
                "speaker": "Katy Huberty, Analyst - Morgan Stanley",
                "text": "Can you talk about iPhone demand in China?",
            },
            {
                "speaker": "Tim Cook",
                "text": "We saw strong demand across emerging markets.",
            },
        ],
    }


def test_get_transcript_parses_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid payload is parsed into a populated :class:`Transcript`."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _build_payload()), captured
    )
    provider = AlphaVantageProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    assert isinstance(transcript, Transcript)
    assert transcript.ticker == "AAPL"
    assert transcript.year == 2024
    assert transcript.quarter == 1
    assert transcript.provider == "alpha_vantage"
    assert transcript.transcript_id == "abc-123"
    assert transcript.title == "Apple Q1 2024 Earnings Call"
    assert len(transcript.turns) == 5

    # The request was issued once and used the expected URL and params.
    assert captured["calls"] == 1
    kwargs = captured["kwargs"]
    assert kwargs["params"]["symbol"] == "AAPL"
    assert kwargs["params"]["quarter"] == "2024Q1"
    assert kwargs["params"]["function"] == "EARNINGS_CALL_TRANSCRIPT"
    assert kwargs["params"]["apikey"] == "key"


def test_get_transcript_section_flips_to_qa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turns after the Q&A marker carry ``section='qa'``."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _build_payload()), captured
    )
    provider = AlphaVantageProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    sections = [turn.section for turn in transcript.turns]
    assert sections[0] == "prepared_remarks"
    assert sections[1] == "prepared_remarks"
    # The Q&A marker turn itself is labeled "qa".
    assert sections[2] == "qa"
    assert sections[3] == "qa"
    assert sections[4] == "qa"


def test_get_transcript_role_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Speakers are mapped to ``ceo``/``cfo``/``analyst``/``operator``."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _build_payload()), captured
    )
    provider = AlphaVantageProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)

    roles = [turn.role for turn in transcript.turns]
    assert roles[0] == "ceo"  # Tim Cook
    assert roles[1] == "cfo"  # Luca Maestri
    assert roles[2] == "operator"
    assert roles[3] == "analyst"  # Katy Huberty
    assert roles[4] == "ceo"


def test_get_transcript_turn_indices_are_sequential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each turn carries its own ``turn_index`` starting from 0."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, _build_payload()), captured
    )
    provider = AlphaVantageProvider(api_key="key")
    transcript = provider.get_transcript("AAPL", 2024, 1)
    assert [t.turn_index for t in transcript.turns] == [0, 1, 2, 3, 4]


# --- Caching -------------------------------------------------------------


def test_cache_hit_avoids_http_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A pre-populated cache short-circuits the HTTP request entirely."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    cache = TranscriptCache()
    provider = AlphaVantageProvider(api_key="key", cache=cache)

    # Seed the cache directly.
    seed_payload = _build_payload()
    transcript = provider._parse_payload(seed_payload, "AAPL", 2024, 1)
    cache.set(transcript)

    captured: dict[str, Any] = {}
    # This fake_get would raise if invoked, so a successful return proves
    # the cache short-circuited the HTTP call.
    def boom(
        self: Any, *args: Any, **kwargs: Any
    ) -> FakeResponse:  # noqa: ARG001
        captured["called"] = True
        raise AssertionError("HTTP should not be called on cache hit")

    monkeypatch.setattr("requests.Session.get", boom, raising=True)

    result = provider.get_transcript("AAPL", 2024, 1)
    assert result.ticker == "AAPL"
    assert captured == {}
