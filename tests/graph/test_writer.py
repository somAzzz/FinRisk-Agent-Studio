"""Unit tests for ``src.graph.writer.GraphWriter`` using a fake client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.graph.writer import GraphWriter
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation

# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


@dataclass
class _Call:
    cypher: str
    parameters: dict[str, Any]


class FakeNeo4jClient:
    """Records every ``run()`` call for later assertions."""

    def __init__(self) -> None:
        self.calls: list[_Call] = []  # populated by run()

    def run(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        self.calls.append(_Call(cypher=cypher, parameters=dict(parameters or {})))
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _evidence(eid: str = "ev-1") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="edgar_corpus",
        source_id="filing-1",
        quote="We depend on TSMC for advanced chips.",
        retrieved_at=datetime(2025, 1, 1, 0, 0, 0),
        confidence=0.9,
    )


def _entity(
    eid: str = "ent-1",
    name: str = "Acme Corp",
    entity_type: str = "company",
    ticker: str = "ACME",
) -> Entity:
    return Entity(
        entity_id=eid,
        name=name,
        entity_type=entity_type,
        normalized_name=name.lower(),
        ticker=ticker,
        confidence=0.95,
    )


def _claim(
    cid: str = "claim-1",
    entities: list[Entity] | None = None,
    evidence: list[Evidence] | None = None,
) -> Claim:
    if evidence is None:
        evidence = [_evidence("ev-claim-1")]
    return Claim(
        claim_id=cid,
        claim_type="supply_chain",
        statement="Acme depends on TSMC.",
        related_risk_ids=["risk-supply"],
        entities=entities or [],
        evidence=evidence,
        confidence=0.8,
    )


def _relation(
    rid: str = "rel-1",
    source: Entity | None = None,
    target: Entity | None = None,
) -> Relation:
    return Relation(
        relation_id=rid,
        source=source or _entity("ent-source", "Source", ticker="SRC"),
        target=target or _entity("ent-target", "Target", ticker="TGT"),
        relation_type="supplies_to",
        evidence=[_evidence("ev-rel-1")],
        confidence=0.7,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_write_entity_merges_with_correct_label_and_props() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    writer.write_entity(_entity())

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "MERGE (n:Company" in call.cypher
    assert "entity_id" in call.cypher
    assert "SET n += $props" in call.cypher
    assert call.parameters == {
        "entity_id": "ent-1",
        "props": {
            "entity_id": "ent-1",
            "name": "Acme Corp",
            "normalized_name": "acme corp",
            "ticker": "ACME",
            "cik": None,
            "aliases": [],
            "metadata": {},
            "confidence": 0.95,
        },
    }
    # The props dict must carry the canonical fields.
    assert call.parameters["props"]["entity_id"] == "ent-1"
    assert call.parameters["props"]["ticker"] == "ACME"
    assert call.parameters["props"]["name"] == "Acme Corp"


def test_write_evidence_merges_on_entity_id() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    writer.write_evidence(_evidence("ev-42"))

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "MERGE (n:Evidence" in call.cypher
    assert "entity_id" in call.cypher
    assert call.parameters["entity_id"] == "ev-42"
    assert call.parameters["props"]["source_type"] == "edgar_corpus"
    assert call.parameters["props"]["quote"].startswith("We depend")


def test_write_relation_writes_endpoints_and_typed_relationship() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    relation = _relation()
    writer.write_relation(relation)

    # Two entity MERGEs + the relationship MERGE.
    assert len(fake.calls) == 3

    label_cyphers = [c.cypher for c in fake.calls[:2]]
    assert any("MERGE (n:Company" in c for c in label_cyphers)

    rel_call = fake.calls[2]
    assert "MATCH (s { entity_id: $source_id })" in rel_call.cypher
    assert "MATCH (t { entity_id: $target_id })" in rel_call.cypher
    assert "MERGE (s)-[r:SUPPLIES_TO" in rel_call.cypher
    assert rel_call.parameters["relation_id"] == "rel-1"
    assert rel_call.parameters["source_id"] == "ent-source"
    assert rel_call.parameters["target_id"] == "ent-target"
    assert rel_call.parameters["props"]["confidence"] == 0.7


def test_write_claim_links_claim_to_evidence() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    claim = _claim(evidence=[_evidence("ev-1"), _evidence("ev-2")])
    writer.write_claim(claim)

    # 1 claim MERGE + 2 evidence MERGEs + 2 SUPPORTED_BY links.
    assert len(fake.calls) == 5

    claim_merges = [c for c in fake.calls if "MERGE (c:Claim" in c.cypher]
    assert len(claim_merges) == 1
    assert claim_merges[0].parameters["entity_id"] == "claim-1"

    evidence_merges = [
        c for c in fake.calls if "MERGE (n:Evidence" in c.cypher
    ]
    assert len(evidence_merges) == 2

    link_calls = [c for c in fake.calls if "SUPPORTED_BY" in c.cypher]
    assert len(link_calls) == 2
    assert {c.parameters["evidence_id"] for c in link_calls} == {"ev-1", "ev-2"}


def test_write_claim_with_no_evidence_does_not_crash() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    claim = _claim(evidence=[])
    writer.write_claim(claim)  # must not raise

    # Only the claim MERGE itself.
    assert len(fake.calls) == 1
    assert "MERGE (c:Claim" in fake.calls[0].cypher


def test_write_extraction_result_writes_everything() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    @dataclass
    class FakeResult:
        entities: list[Entity]
        relations: list[Relation]
        claims: list[Claim]
        evidence: list[Evidence]

    source = _entity("ent-source", "Source", ticker="SRC")
    target = _entity("ent-target", "Target", ticker="TGT")
    rel = _relation(source=source, target=target)
    ev = _evidence("ev-1")
    claim = _claim(entities=[source, target], evidence=[ev])

    writer.write_extraction_result(
        FakeResult(
            entities=[source, target],
            relations=[rel],
            claims=[claim],
            evidence=[ev],
        )
    )

    # Evidence: 1 standalone + 1 from claim + 1 from relation.evidence
    # Entities: 2 from relation endpoints + 2 from claim.entities
    # Relations: 1 relationship merge
    # Claims: 1 claim merge + 1 SUPPORTED_BY link
    claim_merges = [c for c in fake.calls if "MERGE (c:Claim" in c.cypher]
    assert len(claim_merges) == 1

    rel_merges = [
        c for c in fake.calls if "MERGE (s)-[r:" in c.cypher
    ]
    assert len(rel_merges) == 1

    entity_merges = [
        c for c in fake.calls if "MERGE (n:Company" in c.cypher
    ]
    # source + target appear via both the relation write and the claim
    # entity list, so at least two of each call are issued.
    assert len(entity_merges) >= 2

    supported_by = [c for c in fake.calls if "SUPPORTED_BY" in c.cypher]
    assert len(supported_by) == 1


def test_evidence_node_retains_both_entity_id_and_evidence_id() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]
    writer.write_evidence(_evidence("ev-99"))
    call = fake.calls[0]
    assert call.parameters["entity_id"] == "ev-99"
    assert call.parameters["props"]["evidence_id"] == "ev-99"


def test_claim_node_retains_both_entity_id_and_claim_id() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]
    writer.write_claim(_claim(evidence=[]))
    claim_call = next(c for c in fake.calls if "MERGE (c:Claim" in c.cypher)
    assert claim_call.parameters["entity_id"] == "claim-1"
    assert claim_call.parameters["props"]["claim_id"] == "claim-1"


def test_claim_node_persists_related_risk_ids() -> None:
    fake = FakeNeo4jClient()
    writer = GraphWriter(fake)  # type: ignore[arg-type]

    writer.write_claim(_claim())

    claim_call = next(c for c in fake.calls if "MERGE (c:Claim" in c.cypher)
    assert claim_call.parameters["props"]["related_risk_ids"] == ["risk-supply"]
