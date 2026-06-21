"""Tests for the transcript extraction pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.extraction_agent import ExtractionResult
from src.agents.transcript_agent import TranscriptExtractionAgent
from src.pipelines.extract_from_transcript import extract_from_transcript
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation
from src.schemas.transcripts import Transcript, TranscriptTurn


class FakeTranscriptAgent:
    """Minimal stand-in for :class:`TranscriptExtractionAgent`."""

    name = "transcript_extraction"

    def __init__(self, result: ExtractionResult) -> None:
        self._result = result
        self.calls: list[Transcript] = []

    def extract(self, transcript: Transcript) -> ExtractionResult:
        self.calls.append(transcript)
        return self._result


def _evidence(eid: str = "ev1") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="transcript",
        source_id="tx1",
        quote="Management quote.",
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.9,
    )


def _entity(name: str = "Acme") -> Entity:
    return Entity(
        entity_id=f"ent_{name.lower()}",
        name=name,
        entity_type="company",
        normalized_name=name.lower(),
        confidence=1.0,
    )


def _claim(cid: str = "c1", statement: str = "Demand improving.") -> Claim:
    return Claim(
        claim_id=cid,
        claim_type="supply_chain",
        statement=statement,
        evidence=[_evidence()],
        confidence=0.7,
    )


def _turn(index: int, section: str, role: str, speaker: str, text: str) -> TranscriptTurn:
    return TranscriptTurn(
        speaker=speaker,
        role=role,  # type: ignore[arg-type]
        text=text,
        section=section,  # type: ignore[arg-type]
        turn_index=index,
    )


def _transcript() -> Transcript:
    return Transcript(
        ticker="ACME",
        company_name="Acme Inc.",
        year=2024,
        quarter=3,
        provider="test",
        transcript_id="tx1",
        turns=[
            _turn(0, "prepared_remarks", "ceo", "Jane", "Demand improved."),
            _turn(1, "prepared_remarks", "cfo", "John", "Margins expanded."),
            _turn(
                2,
                "qa",
                "analyst",
                "Analyst",
                "Can you comment on capex?",
            ),
            _turn(3, "qa", "cfo", "John", "We are raising capex guidance."),
            _turn(
                4,
                "qa",
                "analyst",
                "Analyst",
                "Any color on supply bottlenecks?",
            ),
            _turn(5, "qa", "cfo", "John", "Lead times are easing."),
        ],
    )


def test_extract_from_transcript_returns_expected_result() -> None:
    relation = Relation(
        relation_id="r1",
        source=_entity("Acme"),
        target=_entity("Supplier"),
        relation_type="depends_on",
        evidence=[_evidence()],
        confidence=0.7,
    )
    result = ExtractionResult(
        entities=[_entity("Acme"), _entity("Supplier")],
        relations=[relation],
        claims=[_claim()],
        evidence=[_evidence()],
    )
    fake = FakeTranscriptAgent(result=result)
    out = extract_from_transcript(_transcript(), extraction_agent=fake)  # type: ignore[arg-type]
    assert out == result
    assert fake.calls and fake.calls[0].transcript_id == "tx1"


def test_extract_from_transcript_handles_no_answered_questions() -> None:
    agent = TranscriptExtractionAgent(llm_client=None)
    transcript = Transcript(
        ticker="ACME",
        year=2024,
        quarter=4,
        provider="test",
        transcript_id="tx2",
        turns=[
            _turn(
                0,
                "qa",
                "analyst",
                "Analyst",
                "What about capex?",
            ),
            _turn(1, "qa", "operator", "Op", "Thank you, next question."),
        ],
    )
    out = extract_from_transcript(transcript, extraction_agent=agent)
    assert out.relations == []
    assert out.entities == []
    assert out.claims == []
