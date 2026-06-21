"""Alpha Vantage earnings-call transcript provider.

The provider talks to Alpha Vantage's ``EARNINGS_CALL_TRANSCRIPT`` endpoint
and normalizes the response into the shared :class:`Transcript` schema. Alpha
Vantage's free tier is heavily rate limited, so callers should expect
:class:`TranscriptRateLimitError` on tight usage windows.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from src.data.transcripts import (
    Transcript,
    TranscriptCache,
    TranscriptMeta,
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
    TranscriptProviderError,
    TranscriptRateLimitError,
    infer_role,
    infer_section,
)
from src.schemas.transcripts import TranscriptTurn

_RATE_LIMIT_NOTE = "call frequency"
_RATE_LIMIT_PHRASES = ("rate limit", "call frequency", "premium")
_NOT_FOUND_NOTE = "transcript not found"
_INFO_NOTE = "information"
_INVALID_API_NOTE = "invalid api"


class AlphaVantageProvider:
    """Earnings-call transcript provider backed by Alpha Vantage.

    Args:
        api_key: Alpha Vantage API key. Falls back to the
            ``ALPHA_VANTAGE_API_KEY`` environment variable when ``None``.
        cache: Optional :class:`TranscriptCache` used to short-circuit HTTP
            calls for previously fetched transcripts.
        session: Optional ``requests.Session`` (mainly for tests).
        timeout: Per-request timeout in seconds.
    """

    provider_name = "alpha_vantage"

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: str | None = None,
        cache: TranscriptCache | None = None,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        env_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        key = api_key if api_key is not None else env_key
        if not key:
            raise TranscriptProviderConfigError(
                "Alpha Vantage API key is required. "
                "Set ALPHA_VANTAGE_API_KEY or pass api_key explicitly."
            )
        self.api_key: str = key
        self.cache: TranscriptCache | None = cache
        self.timeout: float = timeout
        self._session: requests.Session = session or requests.Session()

    @property
    def session(self) -> requests.Session:
        """Return the underlying ``requests.Session`` (mainly for tests)."""
        return self._session

    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        """Return an empty list — Alpha Vantage has no list endpoint."""
        return []

    def _request(self, ticker: str, year: int, quarter: int) -> dict[str, Any]:
        """GET the transcript payload from Alpha Vantage."""
        params = {
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker.upper(),
            "quarter": f"{year}Q{quarter}",
            "apikey": self.api_key,
        }
        response = self._session.get(
            self.BASE_URL, params=params, timeout=self.timeout
        )
        status = response.status_code
        if status == 404:
            raise TranscriptNotFoundError(
                f"Alpha Vantage transcript not found for "
                f"{ticker.upper()} {year}Q{quarter}"
            )
        if status == 429:
            raise TranscriptRateLimitError(
                f"Alpha Vantage rate limit hit for {ticker.upper()}"
            )
        if status >= 400:
            raise TranscriptProviderError(
                f"Alpha Vantage request failed with status {status}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise TranscriptProviderError(
                f"Alpha Vantage returned non-JSON body: {exc}"
            ) from exc
        return payload

    def get_transcript(
        self, ticker: str, year: int, quarter: int
    ) -> Transcript:
        """Return the transcript for ``ticker`` / ``year`` / ``quarter``."""
        ticker_upper = ticker.upper()
        if self.cache is not None:
            cached = self.cache.get(
                self.provider_name, ticker_upper, year, quarter
            )
            if cached is not None:
                return cached

        payload = self._request(ticker_upper, year, quarter)
        self._raise_for_payload(payload, ticker_upper, year, quarter)

        transcript = self._parse_payload(payload, ticker_upper, year, quarter)

        if self.cache is not None:
            self.cache.set(transcript)
        return transcript

    @staticmethod
    def _raise_for_payload(
        payload: Any, ticker: str, year: int, quarter: int
    ) -> None:
        """Translate Alpha Vantage's note/error payloads into typed errors."""
        if not isinstance(payload, dict):
            return
        note = payload.get("Note") or payload.get("Information")
        if isinstance(note, str) and note.strip():
            lowered = note.lower()
            if any(
                phrase in lowered
                for phrase in _RATE_LIMIT_PHRASES
            ) or _INFO_NOTE in lowered:
                raise TranscriptRateLimitError(
                    f"Alpha Vantage rate limit: {note}"
                )
            if _NOT_FOUND_NOTE in lowered:
                raise TranscriptNotFoundError(
                    f"Alpha Vantage transcript not found for "
                    f"{ticker} {year}Q{quarter}: {note}"
                )
        if isinstance(payload.get("Error Message"), str):
            raise TranscriptProviderError(
                f"Alpha Vantage error: {payload['Error Message']}"
            )
        if payload.get("transcript") in (None, []):
            raise TranscriptNotFoundError(
                f"Alpha Vantage returned no transcript for "
                f"{ticker} {year}Q{quarter}"
            )

    @staticmethod
    def _parse_payload(
        payload: dict[str, Any], ticker: str, year: int, quarter: int
    ) -> Transcript:
        """Convert an Alpha Vantage payload into a :class:`Transcript`."""
        raw_turns = payload.get("transcript") or []
        if not isinstance(raw_turns, list):
            raise TranscriptProviderError(
                "Alpha Vantage payload 'transcript' is not a list"
            )

        # Track the first two non-analyst / non-operator speakers so we can
        # fall back to a positional inference (CEO, then CFO) when the
        # provider's speaker strings do not include an explicit title. We
        # also remember each speaker-name -> role mapping so repeated
        # speakers (e.g. the CEO returning for Q&A) keep the same role.
        next_executive_role: str | None = "ceo"
        speaker_role_memory: dict[str, str] = {}

        turns: list[TranscriptTurn] = []
        section: str = "unknown"
        for index, item in enumerate(raw_turns):
            if not isinstance(item, dict):
                continue
            speaker = str(item.get("speaker", "")).strip() or "Unknown"
            text = str(item.get("text", "")).strip()
            section = infer_section(text, section)
            role = infer_role(speaker)
            if role == "unknown" and speaker in speaker_role_memory:
                role = speaker_role_memory[speaker]
            elif (
                role == "unknown"
                and next_executive_role is not None
                and speaker
                and speaker.lower() != "unknown"
            ):
                role = next_executive_role
                speaker_role_memory[speaker] = role
                if next_executive_role == "ceo":
                    next_executive_role = "cfo"
                else:
                    next_executive_role = None
            elif role in {"ceo", "cfo"}:
                speaker_role_memory[speaker] = role
            turns.append(
                TranscriptTurn(
                    speaker=speaker,
                    role=role,
                    text=text,
                    section=section,
                    turn_index=index,
                )
            )

        transcript_id = str(
            payload.get("transcript_id")
            or f"{ticker}-{year}-Q{quarter}"
        )
        title = payload.get("title") or payload.get("name")
        url = payload.get("url")
        return Transcript(
            ticker=ticker,
            year=year,
            quarter=quarter,
            provider=AlphaVantageProvider.provider_name,
            transcript_id=transcript_id,
            title=title,
            url=url,
            turns=turns,
            metadata={"raw_keys": sorted(payload.keys())},
        )
