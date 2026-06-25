"""Financial Modeling Prep earnings-call transcript provider.

Wraps FMP's v3 and v4 transcript endpoints. The v4 endpoint exposes a list
view keyed by symbol, while the v3 endpoint returns transcripts filtered by
symbol/year/quarter.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
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

_LIST_URL = "https://financialmodelingprep.com/api/v4/earning_call_transcript"
_DETAIL_URL = (
    "https://financialmodelingprep.com/api/v3/earning_call_transcript"
)


class FMPProvider:
    """Earnings-call transcript provider backed by Financial Modeling Prep.

    Args:
        api_key: FMP API key. Falls back to ``FMP_API_KEY`` when ``None``.
        cache: Optional :class:`TranscriptCache` to short-circuit HTTP calls.
        session: Optional ``requests.Session`` (mainly for tests).
        timeout: Per-request timeout in seconds.
    """

    provider_name = "fmp"

    def __init__(
        self,
        api_key: str | None = None,
        cache: TranscriptCache | None = None,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("FMP_API_KEY")
        if not key:
            raise TranscriptProviderConfigError(
                "FMP API key is required. Set FMP_API_KEY or pass api_key."
            )
        self.api_key: str = key
        self.cache: TranscriptCache | None = cache
        self.timeout: float = timeout
        self._session: requests.Session = session or requests.Session()

    @property
    def session(self) -> requests.Session:
        """Return the underlying ``requests.Session`` (mainly for tests)."""
        return self._session

    def _request(self, url: str, params: dict[str, Any]) -> Any:
        """GET a URL, mapping HTTP errors to typed exceptions."""
        merged = {**params, "apikey": self.api_key}
        response = self._session.get(url, params=merged, timeout=self.timeout)
        status = response.status_code
        if status == 404:
            raise TranscriptNotFoundError(
                f"FMP resource not found at {response.url}"
            )
        if status == 429:
            raise TranscriptRateLimitError(
                f"FMP rate limit hit at {response.url}"
            )
        if status >= 400:
            raise TranscriptProviderError(
                f"FMP request failed with status {status} at {response.url}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise TranscriptProviderError(
                f"FMP returned non-JSON body: {exc}"
            ) from exc

    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        """Return a list of transcripts available for ``ticker``."""
        payload = self._request(_LIST_URL, {"symbol": ticker.upper()})
        if not isinstance(payload, list):
            return []
        out: list[TranscriptMeta] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                meta = self._meta_from_list_item(item, ticker.upper())
            except (KeyError, TypeError, ValueError):
                continue
            out.append(meta)
        return out

    @staticmethod
    def _meta_from_list_item(
        item: dict[str, Any], ticker: str
    ) -> TranscriptMeta:
        year = int(item.get("year") or item.get("calendarYear") or 0)
        quarter = int(item.get("quarter") or 0)
        published_raw = item.get("date") or item.get("publishedAt")
        published_at: datetime | None = None
        if isinstance(published_raw, str) and published_raw:
            try:
                published_at = datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")
                )
            except ValueError:
                published_at = None
        return TranscriptMeta(
            ticker=ticker,
            year=year,
            quarter=quarter,
            provider=FMPProvider.provider_name,
            title=item.get("title"),
            published_at=published_at,
            transcript_id=str(
                item.get("id")
                or item.get("transcriptId")
                or f"{ticker}-{year}-Q{quarter}"
            ),
            url=item.get("url"),
        )

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

        url = f"{_DETAIL_URL}/{ticker_upper}"
        payload = self._request(
            url, {"quarter": quarter, "year": year}
        )
        if not isinstance(payload, list):
            raise TranscriptProviderError(
                f"FMP detail endpoint returned {type(payload).__name__}"
            )
        match = self._first_match(payload, year, quarter)
        if match is None:
            raise TranscriptNotFoundError(
                f"FMP transcript not found for "
                f"{ticker_upper} {year}Q{quarter}"
            )

        transcript = self._parse_detail(match, ticker_upper, year, quarter)
        if self.cache is not None:
            self.cache.set(transcript)
        return transcript

    @staticmethod
    def _first_match(
        items: list[Any], year: int, quarter: int
    ) -> dict[str, Any] | None:
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                item_year = int(item.get("year") or item.get("calendarYear") or 0)
                item_quarter = int(item.get("quarter") or 0)
            except (TypeError, ValueError):
                continue
            if item_year == year and item_quarter == quarter:
                return item
        return None

    @staticmethod
    def _parse_detail(
        item: dict[str, Any], ticker: str, year: int, quarter: int
    ) -> Transcript:
        """Convert an FMP detail payload into a :class:`Transcript`."""
        raw_turns = item.get("content") or item.get("transcript") or []
        if isinstance(raw_turns, str):
            turns = _split_fmp_turn_text(raw_turns)
        elif isinstance(raw_turns, list):
            string_chunks = [t for t in raw_turns if isinstance(t, str)]
            turns = string_chunks or _split_fmp_turn_text(
                "\n".join(str(t) for t in raw_turns)
            )
        else:
            turns = []

        parsed: list[TranscriptTurn] = []
        section: str = "unknown"
        # Track the first two unknown speakers so we can fall back to a
        # positional inference (CEO, then CFO) when the speaker string does
        # not include an explicit title. Remember each speaker -> role
        # mapping so repeated speakers keep their assigned role.
        next_executive_role: str | None = "ceo"
        speaker_role_memory: dict[str, str] = {}
        for index, raw in enumerate(turns):
            speaker, text = _split_speaker_line(raw)
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
            parsed.append(
                TranscriptTurn(
                    speaker=speaker or "Unknown",
                    role=role,
                    text=text,
                    section=section,
                    turn_index=index,
                )
            )

        published_raw = item.get("date") or item.get("publishedAt")
        published_at: datetime | None = None
        if isinstance(published_raw, str) and published_raw:
            try:
                published_at = datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")
                )
            except ValueError:
                published_at = None

        transcript_id = str(
            item.get("id")
            or item.get("transcriptId")
            or f"{ticker}-{year}-Q{quarter}"
        )
        return Transcript(
            ticker=ticker,
            year=year,
            quarter=quarter,
            provider=FMPProvider.provider_name,
            transcript_id=transcript_id,
            title=item.get("title"),
            url=item.get("url"),
            published_at=published_at,
            turns=parsed,
            metadata={"raw_keys": sorted(item.keys())},
        )


def _split_speaker_line(line: str) -> tuple[str, str]:
    """Split a single FMP turn line into ``(speaker, text)``.

    FMP often encodes each turn as ``"Speaker Name: turn text"``. We accept
    either the colon-separated form or a plain string treated as the body
    with an empty speaker.
    """
    cleaned = line.strip()
    if not cleaned:
        return "", ""
    if ":" in cleaned:
        speaker, _, text = cleaned.partition(":")
        return speaker.strip(), text.strip()
    return "", cleaned


def _split_fmp_turn_text(body: str) -> list[str]:
    """Split a flat FMP transcript body into per-turn strings."""
    if not body:
        return []
    return [chunk.strip() for chunk in body.split("\n") if chunk.strip()]
