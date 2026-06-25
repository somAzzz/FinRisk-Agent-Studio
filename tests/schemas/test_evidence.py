"""Tests for the Evidence schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.evidence import Evidence
from src.schemas.ids import stable_id


def _make_evidence(**overrides: object) -> Evidence:
    base: dict[str, object] = {
        "evidence_id": "ev_001",
        "source_type": "sec_filing",
        "source_id": "0000320193-23-000106",
        "title": "Form 10-K",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        "section": "Risk Factors",
        "speaker": None,
        "quote": "Supply chain disruptions may materially impact results.",
        "retrieved_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "published_at": datetime(2023, 11, 3, tzinfo=timezone.utc),
        "char_start": 100,
        "char_end": 160,
        "confidence": 0.9,
        "metadata": {"lang": "en"},
    }
    base.update(overrides)
    return Evidence(**base)  # type: ignore[arg-type]


class TestConfidenceBoundaries:
    def test_confidence_zero_is_allowed(self) -> None:
        evidence = _make_evidence(confidence=0.0)
        assert evidence.confidence == 0.0

    def test_confidence_one_is_allowed(self) -> None:
        evidence = _make_evidence(confidence=1.0)
        assert evidence.confidence == 1.0

    def test_confidence_below_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_evidence(confidence=-0.1)

    def test_confidence_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_evidence(confidence=1.1)


class TestQuoteValidator:
    def test_empty_quote_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            _make_evidence(quote="")
        assert "non-empty" in str(excinfo.value).lower()

    def test_whitespace_only_quote_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_evidence(quote="   \t\n")


class TestJsonRoundTrip:
    def test_json_round_trip_preserves_fields(self) -> None:
        evidence = _make_evidence()
        payload = evidence.model_dump_json()
        restored = Evidence.model_validate_json(payload)
        assert restored == evidence
        assert restored.quote == evidence.quote
        assert restored.retrieved_at == evidence.retrieved_at


class TestStableEvidenceId:
    def test_stable_evidence_id_is_deterministic(self) -> None:
        parts = ("sec_filing", "0000320193-23-000106", "Risk Factors")
        first = stable_id("ev", *parts)
        second = stable_id("ev", *parts)
        assert first == second
        assert first.startswith("ev_")
        assert len(first.split("_", 1)[1]) == 12


class TestMetadataDefault:
    def test_metadata_defaults_to_empty_dict(self) -> None:
        evidence = Evidence(
            evidence_id="ev_002",
            source_type="transcript",
            source_id="AAPL-Q4-2023",
            quote="We saw strong demand.",
            retrieved_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            confidence=0.8,
        )
        assert evidence.metadata == {}
