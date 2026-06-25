"""Defeatbeta-api provider adapters.

``defeatbeta-api`` (Apache-2.0) is a thin Python wrapper over the
``defeatbeta/yahoo-finance-data`` HuggingFace parquet mirror. It requires
no API key and exposes:

* earnings-call transcripts (full Q&A, with ``speaker`` labels)
* the SEC filing catalog (no bodies)
* financial ratios (TTM PE, ROE, ROIC, PS, PB, debt-to-equity, ...)
* segment / geography / product revenue breakdowns

This module provides:

* :class:`DefeatBetaProvider` — implements the :class:`TranscriptProvider`
  protocol using defeatbeta's transcripts accessor.
* :func:`fetch_filings_catalog_defeatbeta` — returns a list of
  :class:`FilingMetadata` records from defeatbeta's filing catalog.
* :func:`fetch_financial_metrics_defeatbeta` — returns a flat dict of the
  latest available ratio values for a ticker.
* :func:`fetch_revenue_breakdown_defeatbeta` — returns the long-format
  revenue breakdown for a ticker (best-effort; the 0.0.48 upstream has
  a binder bug on the segment/geography/product queries — the helper
  therefore returns ``[]`` for those sub-calls).

Defeatbeta imports are lazy: if the optional dependency is missing,
:class:`DefeatBetaProvider` raises a clear
:class:`TranscriptProviderConfigError` at construction time and the
catalog/metric functions return empty results. The rest of the project
remains importable.
"""

from __future__ import annotations

import math
import os
import re
from datetime import date, datetime
from typing import Any, Literal

from src.data.transcripts import (
    TranscriptCache,
    TranscriptMeta,
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
    TranscriptProviderError,
    infer_role,
)
from src.schemas.filings import FilingMetadata
from src.schemas.transcripts import Transcript, TranscriptTurn

PROVIDER_NAME = "defeatbeta"

# Defeatbeta spells the accessor "earning" (singular) — not "earnings".
# Cache the lazy import so we only attempt it once per process.
_DEFEATBETA_IMPORT_ERROR: Exception | None = None
_TICKER_CLS: Any | None = None


def _ensure_defeatbeta() -> Any:
    """Return the ``Ticker`` class, importing defeatbeta-api lazily.

    Raises :class:`TranscriptProviderConfigError` if the optional dep is
    not installed. Subsequent calls return the cached class without
    re-importing.
    """
    global _DEFEATBETA_IMPORT_ERROR, _TICKER_CLS
    if _TICKER_CLS is not None:
        return _TICKER_CLS
    try:
        from defeatbeta_api.data.ticker import Ticker  # type: ignore[import-not-found]
    except Exception as exc:  # ImportError and any DuckDB/nltk bootstrap failure
        _DEFEATBETA_IMPORT_ERROR = exc
        raise TranscriptProviderConfigError(
            "defeatbeta-api is not available. Install with `uv add defeatbeta-api`."
        ) from exc
    _TICKER_CLS = Ticker
    return _TICKER_CLS


# ---------------------------------------------------------------------------
# Section inference (defeatbeta transcripts lack the canonical
# "Question-and-Answer Session" marker used by FMP; expand the heuristic.)
# ---------------------------------------------------------------------------

_QA_MARKER_RE = re.compile(r"question[- ]and[- ]answer\s+session", re.IGNORECASE)
_QA_SHORT_RE = re.compile(r"\bQ\s*&\s*A\b", re.IGNORECASE)
_QA_OPERATOR_HINTS = (
    # "first question", "first question please", "your first question comes from"
    re.compile(r"\bfirst\s+question\b", re.IGNORECASE),
    # "we will now take questions", "we'll begin the Q&A"
    re.compile(
        r"we(?:'ll|\s+will)\s+now\s+(?:begin|take|open|start).*question",
        re.IGNORECASE,
    ),
    # "operator, may we have the first question please"
    re.compile(r"operator,?\s+may\s+we\s+have\s+the\s+first\s+question", re.IGNORECASE),
    # IR hand-off: "we will now begin the question-and-answer" / "open it up for questions"
    re.compile(r"open\s+(?:it\s+up\s+)?for\s+questions", re.IGNORECASE),
)


def _looks_like_qa_transition(text: str) -> bool:
    """Return True if ``text`` looks like the start of a Q&A section."""
    if not text:
        return False
    if _QA_MARKER_RE.search(text):
        return True
    if _QA_SHORT_RE.search(text):
        return True
    return any(pattern.search(text) for pattern in _QA_OPERATOR_HINTS)


def _parse_report_date(raw: Any) -> datetime | None:
    """Parse defeatbeta's ``report_date`` column (``YYYY-MM-DD`` string)."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _coerce_int(value: Any) -> int | None:
    """Best-effort coerce to ``int``; return None on failure."""
    if value is None:
        return None
    try:
        # numpy ints are subclasses of int but `int(np.int32(x))` is fine.
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Transcript provider
# ---------------------------------------------------------------------------


class DefeatBetaProvider:
    """Earnings-call transcript provider backed by ``defeatbeta-api``.

    Defeatbeta is the only provider in this project that requires no API
    key — it reads from a public HuggingFace parquet mirror. The package
    uses ``DuckDB`` + ``cache_httpfs`` under the hood; first-ticker
    bootstrap can take a few seconds.

    Args:
        cache: Optional :class:`TranscriptCache` to short-circuit HTTP.
        http_proxy: Optional HTTP proxy forwarded to defeatbeta's Ticker.
        log_level: Log level for defeatbeta's logger (default ``"WARNING"``).
        config: Optional defeatbeta ``TickerConfig`` object (escape hatch
            for unusual setups).
    """

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        cache: TranscriptCache | None = None,
        http_proxy: str | None = None,
        log_level: str = "WARNING",
        config: Any | None = None,
    ) -> None:
        # Validate that the optional dep is importable so callers get a
        # clear error early instead of a stack trace deep inside DuckDB.
        _ensure_defeatbeta()
        self.cache: TranscriptCache | None = cache
        self.http_proxy: str | None = http_proxy if http_proxy is not None else os.environ.get("DEFEATBETA_PROXY")
        self.log_level: str = log_level
        self.config: Any = config
        # Cache Ticker instances per symbol to amortise the DuckDB bootstrap.
        self._ticker_cache: dict[str, Any] = {}

    # -- introspection for tests ---------------------------------------

    @property
    def session(self) -> dict[str, Any]:
        """Return the internal Ticker cache (mainly for monkeypatching)."""
        return self._ticker_cache

    def _get_ticker(self, symbol: str) -> Any:
        """Return a cached :class:`Ticker` for ``symbol``."""
        ticker = self._ticker_cache.get(symbol)
        if ticker is not None:
            return ticker
        kwargs: dict[str, Any] = {"log_level": self.log_level}
        if self.http_proxy:
            kwargs["http_proxy"] = self.http_proxy
        if self.config is not None:
            kwargs["config"] = self.config
        Ticker = _ensure_defeatbeta()
        ticker = Ticker(symbol, **kwargs)
        self._ticker_cache[symbol] = ticker
        return ticker

    # -- public API ----------------------------------------------------

    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        """Return a list of transcripts available for ``ticker``.

        Defeatbeta's ``get_transcripts_list`` is fast (it does not pull
        paragraph bodies); we use it as the cheap path that downstream
        callers iterate to decide which quarters to fetch in detail.
        """
        symbol = ticker.upper()
        try:
            df = self._get_ticker(symbol).earning_call_transcripts().get_transcripts_list()
        except Exception as exc:
            raise TranscriptProviderError(f"defeatbeta list_transcripts failed for {symbol}: {exc}") from exc

        if df is None or len(df) == 0:
            return []

        out: list[TranscriptMeta] = []
        # Iterate rows defensively — defeatbeta returns a pandas DataFrame,
        # but we treat it as an iterable of dicts so tests can swap in a
        # plain list[dict] without monkeypatching pandas.
        try:
            records = df.to_dict("records")
        except AttributeError:
            records = list(df)
        for item in records:
            if not isinstance(item, dict):
                continue
            meta = self._meta_from_row(item, symbol)
            if meta is not None:
                out.append(meta)
        return out

    def get_transcript(self, ticker: str, year: int, quarter: int) -> Transcript:
        """Return the transcript for ``ticker`` / ``year`` / ``quarter``."""
        symbol = ticker.upper()
        if self.cache is not None:
            cached = self.cache.get(self.provider_name, symbol, year, quarter)
            if cached is not None:
                return cached

        try:
            df = self._get_ticker(symbol).earning_call_transcripts().get_transcript(year, quarter)
        except Exception as exc:
            raise TranscriptNotFoundError(f"defeatbeta transcript {symbol} {year}Q{quarter} not found: {exc}") from exc

        if df is None or len(df) == 0:
            raise TranscriptNotFoundError(f"defeatbeta transcript {symbol} {year}Q{quarter} returned no rows")

        # Derive metadata from the list endpoint so we can attach the
        # published date and the upstream transcripts_id without a second
        # round-trip — most callers invoke list_transcripts first anyway.
        meta_published: datetime | None = None
        meta_tid: str | None = None
        try:
            listing = self.list_transcripts(symbol)
        except TranscriptProviderError:
            listing = []
        for m in listing:
            if m.year == year and m.quarter == quarter:
                meta_published = m.published_at
                meta_tid = m.transcript_id
                break

        turns = self._parse_turns(df)

        transcript = Transcript(
            ticker=symbol,
            year=year,
            quarter=quarter,
            provider=self.provider_name,
            transcript_id=(meta_tid if meta_tid else f"{symbol}-{year}-Q{quarter}-defeatbeta"),
            title=None,
            url=None,
            published_at=meta_published,
            turns=turns,
            metadata={"source": "defeatbeta-api"},
        )
        if self.cache is not None:
            self.cache.set(transcript)
        return transcript

    # -- internal helpers ----------------------------------------------

    @staticmethod
    def _meta_from_row(row: dict[str, Any], symbol: str) -> TranscriptMeta | None:
        """Map one ``get_transcripts_list`` row to a :class:`TranscriptMeta`."""
        year = _coerce_int(row.get("fiscal_year"))
        quarter = _coerce_int(row.get("fiscal_quarter"))
        if year is None or quarter is None or not (1 <= quarter <= 4):
            return None
        tid_raw = row.get("transcripts_id")
        transcript_id = f"defeatbeta-{tid_raw}" if tid_raw is not None else f"{symbol}-{year}-Q{quarter}-defeatbeta"
        return TranscriptMeta(
            ticker=symbol,
            year=year,
            quarter=quarter,
            provider=PROVIDER_NAME,
            title=None,
            published_at=_parse_report_date(row.get("report_date")),
            transcript_id=str(transcript_id),
            url=None,
        )

    @staticmethod
    def _parse_turns(df: Any) -> list[TranscriptTurn]:
        """Convert a defeatbeta ``get_transcript`` DataFrame to TranscriptTurns.

        Defeatbeta returns ``paragraph_number, speaker, content``. Speaker
        labels are real names (no titles), so we lean on :func:`infer_role`
        plus a positional CEO/CFO fallback: the first unknown speaker is
        treated as CEO, the second as CFO, then everything else is
        ``"unknown"`` (analysts land here unless the speaker string
        contains the literal word "Analyst", which some transcripts use).
        """
        try:
            records = df.to_dict("records")
        except AttributeError:
            records = list(df)

        turns: list[TranscriptTurn] = []
        section = "unknown"
        next_executive_role: str | None = "ceo"
        speaker_role_memory: dict[str, str] = {}
        for index, row in enumerate(records):
            if not isinstance(row, dict):
                continue
            speaker_raw = row.get("speaker") or ""
            content_raw = row.get("content") or ""
            speaker = str(speaker_raw).strip() or "Unknown"
            text = str(content_raw)
            # Skip sponsor/transcript-metadata boilerplate rows that
            # defeatbeta occasionally prefixes.
            if speaker.upper() in {"TRANSCRIPT SPONSOR", "SPONSOR"} and not text:
                continue
            # Section inference: defeatbeta rarely uses the canonical
            # "Question-and-Answer Session" marker, so check a wider set
            # of patterns before falling back to "prepared_remarks".
            if section != "qa" and _looks_like_qa_transition(text):
                section = "qa"
            elif section == "unknown" and text.strip():
                section = "prepared_remarks"
            role = infer_role(speaker)
            if role == "unknown" and speaker in speaker_role_memory:
                role = speaker_role_memory[speaker]
            elif role == "unknown" and next_executive_role is not None and speaker and speaker.lower() != "unknown":
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
                    section=section if section != "unknown" else "prepared_remarks",
                    turn_index=index,
                )
            )
        return turns


# ---------------------------------------------------------------------------
# Filing-catalog adapter
# ---------------------------------------------------------------------------


def fetch_filings_catalog_defeatbeta(
    ticker: str,
    form_types: list[str] | None = None,
    since: date | None = None,
    limit: int | None = None,
) -> list[FilingMetadata]:
    """Return :class:`FilingMetadata` records from defeatbeta's filing catalog.

    Defeatbeta returns a flat DataFrame with one row per filing. We map
    each row to :class:`FilingMetadata` using the SEC archives URL
    defeatbeta already constructs in ``filing_url``.

    Args:
        ticker: Ticker symbol (upper-cased internally).
        form_types: If provided, keep only filings whose ``form_type``
            (case-insensitively) appears in this list.
        since: Drop filings filed strictly before this date.
        limit: Cap the number of records returned (after filtering).
    """
    symbol = ticker.upper()
    try:
        Ticker = _ensure_defeatbeta()
    except TranscriptProviderConfigError:
        return []

    try:
        df = Ticker(symbol, log_level="WARNING").sec_filing()
    except Exception as exc:
        raise TranscriptProviderError(f"defeatbeta sec_filing failed for {symbol}: {exc}") from exc

    if df is None or len(df) == 0:
        return []

    wanted_forms: set[str] | None = {f.upper() for f in form_types} if form_types else None
    out: list[FilingMetadata] = []
    try:
        records = df.to_dict("records")
    except AttributeError:
        records = list(df)
    for row in records:
        if not isinstance(row, dict):
            continue
        form = str(row.get("form_type") or "").upper()
        if wanted_forms is not None and form not in wanted_forms:
            continue
        filing_date_raw = row.get("filing_date")
        if not filing_date_raw:
            continue
        try:
            filing_date_value = date.fromisoformat(str(filing_date_raw))
        except ValueError:
            continue
        if since is not None and filing_date_value < since:
            continue
        accession = row.get("accession_number")
        cik_raw = row.get("cik")
        if not accession or cik_raw is None:
            continue
        # Defeatbeta already strips leading zeros; the schema accepts both.
        cik_padded = str(cik_raw) if str(cik_raw).startswith("0") else str(cik_raw).zfill(10)
        report_date_value: date | None = None
        rd_raw = row.get("report_date")
        if rd_raw:
            try:
                report_date_value = date.fromisoformat(str(rd_raw))
            except ValueError:
                report_date_value = None
        url = str(row.get("filing_url") or "")
        # The SEC archive URL ends with the accession-no-dashes + primary
        # document; defeatbeta omits the primary document, so we leave
        # ``primary_document`` empty (FilingFetcher will resolve it via
        # the index when it downloads the body).
        out.append(
            FilingMetadata(
                cik=cik_padded,
                accession_number=str(accession),
                form_type=form,
                filing_date=filing_date_value,
                report_date=report_date_value,
                primary_document="",
                url=url,
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Metrics / ratios adapter
# ---------------------------------------------------------------------------

# Each entry: (ratio key, ticker method name, value column in the returned DataFrame)
_RATIO_METHODS: list[tuple[str, str, str]] = [
    ("ttm_pe", "ttm_pe", "ttm_pe"),
    ("ps_ratio", "ps_ratio", "ps_ratio"),
    ("pb_ratio", "pb_ratio", "pb_ratio"),
    ("peg_ratio_by_eps", "peg_ratio", "peg_ratio_by_eps"),
    ("roe", "roe", "roe"),
    ("roic", "roic", "roic"),
    ("debt_to_equity", "debt_to_equity", "debt_to_equity"),
]


def _latest_value(df: Any, value_col: str) -> float | None:
    """Return the most recent non-null value from a defeatbeta ratio DataFrame.

    Defeatbeta returns time series; callers want the latest observation.
    Defeatbeta sorts ascending by ``report_date`` so we take ``iloc[-1]``
    and guard against NaN/None.
    """
    if df is None or len(df) == 0:
        return None
    try:
        rows = df.to_dict("records")
    except AttributeError:
        rows = list(df)
    if not rows:
        return None
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        if value_col not in row:
            continue
        value = row[value_col]
        if value is None:
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(result):
            continue
        return result
    return None


def fetch_financial_metrics_defeatbeta(
    ticker: str,
) -> dict[str, float | None]:
    """Return the latest available ratio values for ``ticker``.

    Keys returned: ``ttm_pe``, ``ps_ratio``, ``pb_ratio``,
    ``peg_ratio_by_eps``, ``roe``, ``roic``, ``debt_to_equity``.

    Missing or broken upstream queries degrade to ``None`` rather than
    raising — callers can still get partial coverage. ``wacc()`` is
    intentionally not called because the 0.0.48 upstream has a bug on
    that query (raises ``KeyError: 'bc10_year'``).
    """
    symbol = ticker.upper()
    try:
        Ticker = _ensure_defeatbeta()
    except TranscriptProviderConfigError:
        return {key: None for key, _, _ in _RATIO_METHODS}

    try:
        t = Ticker(symbol, log_level="WARNING")
    except Exception:
        return {key: None for key, _, _ in _RATIO_METHODS}

    metrics: dict[str, float | None] = {}
    for key, method_name, value_col in _RATIO_METHODS:
        method = getattr(t, method_name, None)
        if method is None:
            metrics[key] = None
            continue
        try:
            df = method()
        except Exception:  # defeatbeta raises on missing data
            metrics[key] = None
            continue
        metrics[key] = _latest_value(df, value_col)
    return metrics


# ---------------------------------------------------------------------------
# Revenue breakdown adapter (best-effort; 0.0.48 upstream is buggy)
# ---------------------------------------------------------------------------


def fetch_revenue_breakdown_defeatbeta(
    ticker: str,
    breakdown: Literal["segment", "geography", "product"] = "segment",
    period_type: Literal["quarterly", "trailing"] = "quarterly",
) -> list[dict[str, Any]]:
    """Return the long-format revenue breakdown for ``ticker``.

    Note (2026-06-25): ``defeatbeta-api`` 0.0.48 has a binder error on
    ``revenue_by_segment``, ``revenue_by_geography`` and
    ``revenue_by_product`` (``Referenced column "breakdown_type" not
    found in FROM clause``). This helper therefore returns ``[]`` for
    those sub-calls and logs a single warning at the call site. Once
    the package is upgraded past 0.0.54 (which unifies these into
    ``revenue_by_breakdown``), the implementation can be revisited.
    """
    symbol = ticker.upper()
    try:
        Ticker = _ensure_defeatbeta()
    except TranscriptProviderConfigError:
        return []
    method_name = f"revenue_by_{breakdown}"
    try:
        t = Ticker(symbol, log_level="WARNING")
        method = getattr(t, method_name, None)
        if method is None:
            return []
        df = method()
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []
    try:
        records = df.to_dict("records")
    except AttributeError:
        records = list(df)
    out: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        # Filter by period_type defensively — defeatbeta stores both
        # quarterly and trailing rows in the same frame.
        if period_type and str(row.get("period_type") or "").lower() != period_type:
            continue
        out.append(
            {
                "breakdown": row.get("breakdown"),
                "breakdown_name": row.get("breakdown_name"),
                "value_type": row.get("value_type"),
                "period_type": row.get("period_type"),
                "report_date": row.get("report_date"),
                "value": row.get("value"),
            }
        )
    return out


__all__ = [
    "PROVIDER_NAME",
    "DefeatBetaProvider",
    "fetch_filings_catalog_defeatbeta",
    "fetch_financial_metrics_defeatbeta",
    "fetch_revenue_breakdown_defeatbeta",
]
