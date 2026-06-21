"""Tests for :mod:`src.evaluation.extraction_eval`."""

from __future__ import annotations

from datetime import datetime, timezone

from src.evaluation.extraction_eval import evaluate_extraction
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation


def _evidence(eid: str, quote: str = "quote") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id=f"src-{eid}",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
    )


def _entity(eid: str, name: str = "Entity") -> Entity:
    return Entity(
        entity_id=eid,
        name=name,
        entity_type="company",
        normalized_name=name.lower(),
        confidence=0.9,
    )


def _relation(rid: str, source: Entity, target: Entity) -> Relation:
    return Relation(
        relation_id=rid,
        source=source,
        target=target,
        relation_type="subsidiary_of",
        evidence=[_evidence(f"ev-{rid}")],
        confidence=0.7,
    )


def _claim(cid: str, with_evidence: bool) -> Claim:
    return Claim(
        claim_id=cid,
        claim_type="risk",
        statement=f"statement {cid}",
        evidence=[_evidence(f"ev-{cid}")] if with_evidence else [],
        confidence=0.5,
    )


def test_entity_matching_counts_overlap() -> None:
    expected = [_entity("e1"), _entity("e2"), _entity("e3")]
    predicted = [_entity("e1"), _entity("e2"), _entity("e4")]
    result = evaluate_extraction(
        predicted_entities=predicted,
        predicted_relations=[],
        predicted_claims=[],
        expected_entities=expected,
        expected_relations=[],
        expected_claims=[],
    )
    assert result.expected_entities == 3
    assert result.matched_entities == 2
    assert result.total_predicted_entities == 3


def test_relation_matching_counts_overlap() -> None:
    a, b, c = _entity("a"), _entity("b"), _entity("c")
    expected_relations = [_relation("r1", a, b), _relation("r2", b, c)]
    predicted_relations = [_relation("r1", a, b), _relation("r3", a, c)]
    result = evaluate_extraction(
        predicted_entities=[],
        predicted_relations=predicted_relations,
        predicted_claims=[],
        expected_entities=[],
        expected_relations=expected_relations,
        expected_claims=[],
    )
    assert result.expected_relations == 2
    assert result.matched_relations == 1
    assert result.total_predicted_relations == 2


def test_unsupported_claim_count() -> None:
    claims = [_claim("c1", True), _claim("c2", False), _claim("c3", False)]
    result = evaluate_extraction(
        predicted_entities=[],
        predicted_relations=[],
        predicted_claims=claims,
        expected_entities=[],
        expected_relations=[],
        expected_claims=[],
    )
    assert result.unsupported_claims == 2
    assert result.total_predicted_claims == 3


def test_evidence_coverage_computation() -> None:
    expected_entities = [_entity("e1"), _entity("e2")]
    expected_relations = [
        _relation("r1", expected_entities[0], expected_entities[1]),
    ]
    predicted_entities = [_entity("e1")]  # half
    predicted_relations = [_relation("r1", expected_entities[0], expected_entities[1])]
    result = evaluate_extraction(
        predicted_entities=predicted_entities,
        predicted_relations=predicted_relations,
        predicted_claims=[],
        expected_entities=expected_entities,
        expected_relations=expected_relations,
        expected_claims=[],
    )
    # 2 expected entities + 1 expected relation = 3 expected total.
    # 1 entity matched + 1 relation matched = 2/3 rounded to 4dp = 0.6667.
    assert result.evidence_coverage == 0.6667


def test_evidence_coverage_is_zero_when_nothing_matches() -> None:
    expected_entities = [_entity("e1"), _entity("e2")]
    expected_relations = [
        _relation("r1", expected_entities[0], expected_entities[1]),
    ]
    result = evaluate_extraction(
        predicted_entities=[_entity("e9")],
        predicted_relations=[],
        predicted_claims=[],
        expected_entities=expected_entities,
        expected_relations=expected_relations,
        expected_claims=[],
    )
    assert result.evidence_coverage == 0.0


def test_evidence_coverage_is_one_when_full_match() -> None:
    entities = [_entity("e1"), _entity("e2")]
    relations = [_relation("r1", entities[0], entities[1])]
    result = evaluate_extraction(
        predicted_entities=entities,
        predicted_relations=relations,
        predicted_claims=[],
        expected_entities=entities,
        expected_relations=relations,
        expected_claims=[],
    )
    assert result.evidence_coverage == 1.0
