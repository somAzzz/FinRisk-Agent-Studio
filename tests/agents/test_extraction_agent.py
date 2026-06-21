"""Tests for the generic extraction agent and chunking helper."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.agents.extraction_agent import (
    ExtractionAgent,
    ExtractionResult,
    chunk_text,
)
from src.agents.state import AgentState
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence


def _evidence(eid: str = "ev1", quote: str = "Some quote.") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id="src",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.9,
    )


def test_chunk_text_char_offsets_align() -> None:
    text = "abcdefghij" * 100  # 1000 chars
    chunks = chunk_text(
        text=text,
        source_id="src",
        source_type="sec_filing",
        section="section_1",
        chunk_size=300,
        overlap=50,
    )
    assert chunks, "chunk_text must return at least one chunk"
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_chunk_text_preserves_overlap_content() -> None:
    text = "abcdefghij" * 200  # 2000 chars
    chunks = chunk_text(
        text=text,
        source_id="src",
        source_type="sec_filing",
        section="section_1",
        chunk_size=500,
        overlap=100,
    )
    assert len(chunks) >= 2
    first, second = chunks[0], chunks[1]
    overlap_text = text[first.char_end - 100 : first.char_end]
    assert overlap_text in second.text


def test_chunk_text_returns_zero_width_chunk_for_empty_text() -> None:
    chunks = chunk_text(
        text="",
        source_id="src",
        source_type="sec_filing",
        section="section_1",
    )
    assert len(chunks) == 1
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 0


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_text(
            text="hello world",
            source_id="src",
            source_type="sec_filing",
            chunk_size=100,
            overlap=100,
        )


def test_extraction_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(
            {
                "entities": [],
                "relations": [],
                "claims": [],
                "evidence": [],
                "warnings": [],
                "extra": "no",
            }
        )


def test_extraction_result_json_round_trip() -> None:
    entity = Entity(
        entity_id="ent_1",
        name="Acme",
        entity_type="company",
        normalized_name="acme",
        confidence=1.0,
    )
    result = ExtractionResult(
        entities=[entity],
        relations=[],
        claims=[],
        evidence=[_evidence()],
        warnings=["warn"],
    )
    payload = result.model_dump_json()
    again = ExtractionResult.model_validate_json(payload)
    assert again == result


def test_extraction_agent_no_llm_appends_note_and_returns_state() -> None:
    state = AgentState(
        goal="extract",
        evidence=[_evidence(quote="A quote that would be chunked.")],
    )
    agent = ExtractionAgent(llm_client=None)
    out = agent.run(state)
    assert out is state
    assert out.entities == []
    assert out.relations == []
    assert out.claims == []
    assert any("no llm_client" in n for n in out.notes)
