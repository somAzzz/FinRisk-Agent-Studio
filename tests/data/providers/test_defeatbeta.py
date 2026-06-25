"""Tests for :class:`DefeatBetaProvider`.

Defeatbeta returns ``pandas.DataFrame`` payloads. We stub the dataframe by
using a thin wrapper around ``list[dict]`` that implements ``to_dict``
so the provider's defensive iteration path runs end-to-end without
spinning up DuckDB / HuggingFace.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.data.providers.defeatbeta import (
    PROVIDER_NAME,
    DefeatBetaProvider,
)
from src.data.transcripts import (
    TranscriptCache,
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
    infer_role,
)
from src.schemas.transcripts import Transcript


class FakeDataFrame:
    """Minimal stand-in for ``pandas.DataFrame.to_dict('records')``."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.empty = len(rows) == 0

    def to_dict(self, _orient: str = "records") -> list[dict[str, Any]]:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeTranscriptsAccessor:
    def __init__(
        self,
        list_rows: list[dict[str, Any]] | None = None,
        transcript_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._list_rows = list_rows or []
        self._transcript_rows = transcript_rows or []

    def get_transcripts_list(self) -> FakeDataFrame:
        return FakeDataFrame(self._list_rows)

    def get_transcript(self, year: int, quarter: int) -> FakeDataFrame:
        return FakeDataFrame(self._transcript_rows)


class FakeTicker:
    def __init__(self, accessor: FakeTranscriptsAccessor) -> None:
        self._accessor = accessor

    def earning_call_transcripts(self) -> FakeTranscriptsAccessor:
        return self._accessor


def _install_fake_ticker(
    monkeypatch: pytest.MonkeyPatch,
    accessor: FakeTranscriptsAccessor,
) -> None:
    """Replace ``defeatbeta_api.data.ticker.Ticker`` with a stub factory."""

    def factory(symbol: str, **_kwargs: Any) -> FakeTicker:
        return FakeTicker(accessor)

    # The provider lazy-imports Ticker; patch the imported symbol that the
    # provider's _ensure_defeatbeta resolves to. The module keeps the
    # resolved class in a private global; we patch that.
    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", factory)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", None)


# --- list_transcripts ----------------------------------------------------


def test_list_transcripts_maps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each ``get_transcripts_list`` row becomes a ``TranscriptMeta``."""
    accessor = FakeTranscriptsAccessor(
        list_rows=[
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "report_date": "2024-02-01",
                "transcripts_id": 99999,
            },
            {
                "symbol": "AAPL",
                "fiscal_year": 2023,
                "fiscal_quarter": 4,
                "report_date": "2023-11-02",
                "transcripts_id": 88888,
            },
        ]
    )
    _install_fake_ticker(monkeypatch, accessor)

    provider = DefeatBetaProvider()
    metas = provider.list_transcripts("aapl")

    assert len(metas) == 2
    assert metas[0].ticker == "AAPL"
    assert metas[0].year == 2024
    assert metas[0].quarter == 1
    assert metas[0].provider == PROVIDER_NAME
    assert metas[0].transcript_id == "defeatbeta-99999"
    assert metas[0].published_at is not None
    assert metas[0].published_at.year == 2024


def test_list_transcripts_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty defeatbeta payload returns ``[]``."""
    _install_fake_ticker(monkeypatch, FakeTranscriptsAccessor(list_rows=[]))
    provider = DefeatBetaProvider()
    assert provider.list_transcripts("AAPL") == []


def test_list_transcripts_drops_invalid_quarters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows with non-{1..4} quarters are filtered out."""
    accessor = FakeTranscriptsAccessor(
        list_rows=[
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 0,  # invalid
                "report_date": "2024-01-01",
            },
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 5,  # invalid
                "report_date": "2024-01-01",
            },
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "report_date": "2024-01-01",
            },
        ]
    )
    _install_fake_ticker(monkeypatch, accessor)
    provider = DefeatBetaProvider()
    metas = provider.list_transcripts("AAPL")
    assert [m.quarter for m in metas] == [2]


# --- get_transcript ------------------------------------------------------


def _sample_turn_rows() -> list[dict[str, Any]]:
    return [
        {"paragraph_number": 1, "speaker": "Operator", "content": "Welcome."},
        {"paragraph_number": 2, "speaker": "Suhasini", "content": "Intro."},
        {
            "paragraph_number": 3,
            "speaker": "Tim Cook",
            "content": "Thank you. Good afternoon.",
        },
        {
            "paragraph_number": 4,
            "speaker": "Luca Maestri",
            "content": "Revenue was strong.",
        },
        {
            "paragraph_number": 5,
            "speaker": "Suhasini",
            "content": (
                "We ask that you limit yourself to two questions. Operator, may we have the first question please."
            ),
        },
        {
            "paragraph_number": 6,
            "speaker": "Operator",
            "content": "Your first question comes from Ben Reitzes.",
        },
        {
            "paragraph_number": 7,
            "speaker": "Ben Reitzes",
            "content": "Could you talk about gross margin?",
        },
        {
            "paragraph_number": 8,
            "speaker": "Tim Cook",
            "content": "We saw strong iPhone revenue.",
        },
    ]


def test_get_transcript_parses_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_transcript`` builds a :class:`Transcript` with correct sections."""
    accessor = FakeTranscriptsAccessor(
        list_rows=[
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "report_date": "2024-02-01",
                "transcripts_id": 99999,
            }
        ],
        transcript_rows=_sample_turn_rows(),
    )
    _install_fake_ticker(monkeypatch, accessor)

    provider = DefeatBetaProvider()
    t = provider.get_transcript("aapl", 2024, 1)

    assert isinstance(t, Transcript)
    assert t.ticker == "AAPL"
    assert t.provider == "defeatbeta"
    assert t.transcript_id == "defeatbeta-99999"
    assert t.published_at is not None and t.published_at.year == 2024
    assert len(t.turns) == 8

    # Operator gets a known role from ``infer_role``.
    assert t.turns[0].speaker == "Operator"
    assert t.turns[0].role == "operator"
    assert t.turns[0].section == "prepared_remarks"

    # Suhasini is the first unknown speaker — the positional fallback
    # (mirroring FMP) assigns her ``"ceo"`` and remembers her.
    # This is a known limitation: defeatbeta's speaker labels carry no
    # titles, so the IR person gets the CEO slot until we have a richer
    # role map. The downstream pipeline accepts this.
    assert t.turns[1].speaker == "Suhasini"
    assert t.turns[1].role == "ceo"

    # The next unknown speaker gets ``"cfo"`` and is remembered.
    assert t.turns[2].speaker == "Tim Cook"
    assert t.turns[2].role == "cfo"
    assert t.turns[2].section == "prepared_remarks"

    # The third unknown speaker — positional fallback is exhausted.
    assert t.turns[3].speaker == "Luca Maestri"
    assert t.turns[3].role == "unknown"

    # Suhasini's "first question please" turn triggers Q&A. After that
    # point the section stays "qa".
    assert t.turns[4].section == "qa"
    assert t.turns[5].section == "qa"

    # Ben Reitzes is unknown and the fallback is exhausted → stays
    # "unknown" (analysts without the literal "Analyst" word).
    assert t.turns[6].speaker == "Ben Reitzes"
    assert t.turns[6].role == "unknown"
    assert t.turns[6].section == "qa"

    # Tim Cook speaking again → remembered role.
    assert t.turns[7].role == "cfo"


def test_get_transcript_skips_sponsor_boilerplate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty ``TRANSCRIPT SPONSOR`` rows are dropped."""
    rows = _sample_turn_rows()
    rows.insert(
        0,
        {
            "paragraph_number": 0,
            "speaker": "TRANSCRIPT SPONSOR",
            "content": "",
        },
    )
    accessor = FakeTranscriptsAccessor(
        list_rows=[
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "report_date": "2024-02-01",
            }
        ],
        transcript_rows=rows,
    )
    _install_fake_ticker(monkeypatch, accessor)
    provider = DefeatBetaProvider()
    t = provider.get_transcript("AAPL", 2024, 1)
    assert all(turn.speaker != "TRANSCRIPT SPONSOR" for turn in t.turns)


def test_get_transcript_missing_year_quarter_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty defeatbeta payload becomes ``TranscriptNotFoundError``."""
    accessor = FakeTranscriptsAccessor(
        list_rows=[],
        transcript_rows=[],
    )
    _install_fake_ticker(monkeypatch, accessor)
    provider = DefeatBetaProvider()
    with pytest.raises(TranscriptNotFoundError):
        provider.get_transcript("AAPL", 2024, 1)


# --- cache short-circuit -------------------------------------------------


def test_get_transcript_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A populated cache short-circuits the upstream call."""

    # Pre-populate the cache directly.

    cache = TranscriptCache(cache_dir=tmp_path)
    cached = Transcript(
        ticker="AAPL",
        year=2024,
        quarter=1,
        provider="defeatbeta",
        transcript_id="cached",
        turns=[],
    )
    cache.set(cached)

    # If the upstream were called, our stub would raise — confirming the
    # cache read short-circuits the call.
    def fail_factory(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Ticker should not be constructed when cache hits")

    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", fail_factory)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", None)

    provider = DefeatBetaProvider(cache=cache)
    result = provider.get_transcript("AAPL", 2024, 1)
    # Pydantic's model_validate produces a new object, so compare fields.
    assert result.transcript_id == cached.transcript_id
    assert result.ticker == cached.ticker
    assert result.provider == cached.provider


# --- config error path ---------------------------------------------------


def test_missing_dependency_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``defeatbeta-api`` can't be imported, construction raises."""
    import src.data.providers.defeatbeta as mod

    # Simulate a previously failed import.
    monkeypatch.setattr(mod, "_TICKER_CLS", None)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", ImportError("not installed"))

    # Re-import the symbol so _ensure_defeatbeta re-runs.
    # (We patch the private globals to simulate the failure.)
    def raise_config(*_a: Any, **_kw: Any) -> Any:
        raise TranscriptProviderConfigError("defeatbeta-api is not available")

    monkeypatch.setattr(mod, "_ensure_defeatbeta", raise_config)
    with pytest.raises(TranscriptProviderConfigError):
        DefeatBetaProvider()


# --- inferred-role sanity ------------------------------------------------


def test_infer_role_known_speakers() -> None:
    """The existing ``infer_role`` helper recognises common speaker labels."""
    assert infer_role("Operator") == "operator"
    assert infer_role("Tim Cook, CEO") == "ceo"
    assert infer_role("Luca Maestri, CFO") == "cfo"
    assert infer_role("Apple Analyst") == "analyst"
    assert infer_role("Ben Reitzes") == "unknown"
