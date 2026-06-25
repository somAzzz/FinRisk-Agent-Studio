"""Tests for the Entity schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.entities import Entity
from src.schemas.evidence import Evidence


def _make_entity(**overrides: object) -> Entity:
    base: dict[str, object] = {
        "entity_id": "ent_001",
        "name": "Apple Inc.",
        "entity_type": "company",
        "normalized_name": "apple inc",
        "ticker": "AAPL",
        "cik": "0000320193",
        "confidence": 0.95,
    }
    base.update(overrides)
    return Entity(**base)  # type: ignore[arg-type]


class TestConfidenceBoundaries:
    def test_confidence_zero_is_allowed(self) -> None:
        assert _make_entity(confidence=0.0).confidence == 0.0

    def test_confidence_one_is_allowed(self) -> None:
        assert _make_entity(confidence=1.0).confidence == 1.0

    def test_confidence_below_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_entity(confidence=-0.01)

    def test_confidence_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_entity(confidence=1.01)


class TestDefaults:
    def test_aliases_default_to_empty_list(self) -> None:
        entity = _make_entity()
        assert entity.aliases == []
        assert entity.aliases is not _make_entity().aliases

    def test_metadata_default_to_empty_dict(self) -> None:
        entity = _make_entity()
        assert entity.metadata == {}

    def test_evidence_default_to_empty_list(self) -> None:
        entity = _make_entity()
        assert entity.evidence == []

    def test_explicit_aliases_are_preserved(self) -> None:
        entity = _make_entity(aliases=["AAPL", "Apple Computer"])
        assert entity.aliases == ["AAPL", "Apple Computer"]


class TestJsonRoundTrip:
    def test_json_round_trip_without_evidence(self) -> None:
        entity = _make_entity()
        payload = entity.model_dump_json()
        restored = Entity.model_validate_json(payload)
        assert restored == entity

    def test_json_round_trip_with_evidence(self) -> None:
        evidence = Evidence(
            evidence_id="ev_001",
            source_type="sec_filing",
            source_id="0000320193-23-000106",
            quote="Apple Inc. designs consumer electronics.",
            retrieved_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            confidence=0.9,
        )
        entity = _make_entity(evidence=[evidence])
        payload = entity.model_dump_json()
        restored = Entity.model_validate_json(payload)
        assert restored == entity
        assert len(restored.evidence) == 1
        assert restored.evidence[0] == evidence
