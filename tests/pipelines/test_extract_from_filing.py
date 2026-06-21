"""Tests for the filing extraction pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.extraction_agent import ExtractionResult
from src.agents.filing_agent import FilingExtractionAgent
from src.pipelines.extract_from_filing import extract_from_filing
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.filings import FilingRecord
from src.schemas.relations import Relation


class FakeFilingAgent:
    """Minimal stand-in for :class:`FilingExtractionAgent`."""

    name = "filing_extraction"

    def __init__(self, result: ExtractionResult) -> None:
        self._result = result
        self.calls: list[FilingRecord] = []

    def extract(self, filing: FilingRecord) -> ExtractionResult:
        self.calls.append(filing)
        return self._result


def _evidence(eid: str = "ev1") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id="src",
        quote="Some quote from the filing.",
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


def _claim(cid: str = "c1") -> Claim:
    return Claim(
        claim_id=cid,
        claim_type="risk",
        statement="Some risk",
        evidence=[_evidence()],
        confidence=0.7,
    )


def _filing(sections: dict[str, str] | None = None) -> FilingRecord:
    return FilingRecord(
        source="sec",
        cik="0001",
        ticker="ACME",
        company_name="Acme Inc.",
        form_type="10-K",
        year=2024,
        sections=sections or {"section_1A": "Risk factors text."},
    )


def test_extract_from_filing_returns_expected_result() -> None:
    relation = Relation(
        relation_id="r1",
        source=_entity("Acme"),
        target=_entity("Supplier"),
        relation_type="supplies_to",
        evidence=[_evidence()],
        confidence=0.7,
    )
    result = ExtractionResult(
        entities=[_entity("Acme"), _entity("Supplier")],
        relations=[relation],
        claims=[_claim()],
        evidence=[_evidence()],
    )
    fake = FakeFilingAgent(result=result)
    out = extract_from_filing(_filing(), extraction_agent=fake)  # type: ignore[arg-type]
    assert out == result
    assert fake.calls and fake.calls[0].cik == "0001"


def test_extract_from_filing_drops_relations_without_evidence() -> None:
    relation_with = Relation(
        relation_id="r1",
        source=_entity("Acme"),
        target=_entity("Supplier"),
        relation_type="supplies_to",
        evidence=[_evidence()],
        confidence=0.7,
    )
    relation_without = Relation(
        relation_id="r2",
        source=_entity("Acme"),
        target=_entity("Customer"),
        relation_type="customer_of",
        evidence=[],
        confidence=0.7,
    )
    result = ExtractionResult(
        entities=[_entity("Acme"), _entity("Supplier"), _entity("Customer")],
        relations=[relation_with, relation_without],
        claims=[],
        evidence=[],
    )
    fake = FakeFilingAgent(result=result)
    out = extract_from_filing(_filing(), extraction_agent=fake)  # type: ignore[arg-type]
    assert [r.relation_id for r in out.relations] == ["r1"]
    assert any("dropped" in w for w in out.warnings)


def test_extract_from_filing_handles_empty_sections() -> None:
    agent = FilingExtractionAgent(llm_client=None)
    out = extract_from_filing(_filing(sections={}), extraction_agent=agent)
    assert out.entities == []
    assert out.relations == []
    assert out.claims == []
    assert out.evidence == []
