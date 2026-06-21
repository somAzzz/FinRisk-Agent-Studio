"""Unit tests for ``src.graph.queries`` using a fake Neo4j client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from src.graph.queries import (
    CompanyExposure,
    GraphPath,
    get_claim_evidence,
    get_downstream_customers,
    get_geopolitical_exposures,
    get_policy_beneficiaries,
    get_upstream_suppliers,
)
from src.schemas.evidence import Evidence


# ---------------------------------------------------------------------------
# Fake client and helpers
# ---------------------------------------------------------------------------


@dataclass
class _Call:
    cypher: str
    parameters: dict[str, Any]


class FakeNeo4jClient:
    """Returns a configurable list of records per cypher substring."""

    def __init__(self, results: list[dict] | None = None) -> None:
        self.calls: list[_Call] = []
        self._results = results or []

    def run(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        self.calls.append(_Call(cypher=cypher, parameters=dict(parameters or {})))
        return list(self._results)


def _evidence_dict(eid: str, quote: str = "q") -> dict[str, Any]:
    return {
        "evidence_id": eid,
        "source_type": "edgar_corpus",
        "source_id": "filing-1",
        "title": None,
        "url": None,
        "section": None,
        "speaker": None,
        "quote": quote,
        "retrieved_at": datetime(2025, 1, 1, 0, 0, 0),
        "published_at": None,
        "char_start": None,
        "char_end": None,
        "confidence": 0.9,
        "metadata": {},
    }


def _entity_dict(
    eid: str = "ent-1",
    name: str = "Acme Corp",
    entity_type: str = "company",
    ticker: str | None = "ACME",
) -> dict[str, Any]:
    return {
        "entity_id": eid,
        "name": name,
        "entity_type": entity_type,
        "normalized_name": name.lower(),
        "ticker": ticker,
        "cik": None,
        "aliases": [],
        "metadata": {},
        "evidence": [],
        "confidence": 0.9,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_upstream_suppliers_issues_correct_cypher_and_parses_path() -> None:
    # Build a fake Neo4j path object with .nodes and .relationships.
    supplier_node = SimpleNamespace(**_entity_dict("ent-sup", "Supplier"))
    acme_node = SimpleNamespace(**_entity_dict("ent-acme", "Acme"))
    rel_obj = SimpleNamespace(type="SUPPLIES_TO")
    path = SimpleNamespace(nodes=[supplier_node, acme_node], relationships=[rel_obj])
    fake = FakeNeo4jClient(results=[{"p": path}])

    paths = get_upstream_suppliers(fake, "ACME", depth=3)  # type: ignore[arg-type]

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "MATCH (c:Company { ticker: $ticker })" in call.cypher
    assert "SUPPLIES_TO|BUYS_FROM" in call.cypher
    assert "1..3" in call.cypher
    assert call.parameters == {"ticker": "ACME"}

    assert len(paths) == 1
    assert isinstance(paths[0], GraphPath)
    assert [n.entity_id for n in paths[0].nodes] == ["ent-sup", "ent-acme"]
    assert paths[0].relations == ["SUPPLIES_TO"]


def test_get_downstream_customers_parses_path() -> None:
    acme = SimpleNamespace(**_entity_dict("ent-acme", "Acme"))
    customer = SimpleNamespace(**_entity_dict("ent-cust", "Customer"))
    rel_obj = SimpleNamespace(type="CUSTOMER_OF")
    path = SimpleNamespace(nodes=[acme, customer], relationships=[rel_obj])
    fake = FakeNeo4jClient(results=[{"p": path}])

    paths = get_downstream_customers(fake, "ACME", depth=2)  # type: ignore[arg-type]

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "CUSTOMER_OF" in call.cypher
    assert "1..2" in call.cypher
    assert call.parameters == {"ticker": "ACME"}

    assert [n.entity_id for n in paths[0].nodes] == ["ent-acme", "ent-cust"]
    assert paths[0].relations == ["CUSTOMER_OF"]


def test_get_claim_evidence_returns_list_of_evidence() -> None:
    records = [
        {"e": _evidence_dict("ev-1", "first quote")},
        {"e": _evidence_dict("ev-2", "second quote")},
    ]
    fake = FakeNeo4jClient(results=records)

    evidence = get_claim_evidence(fake, "claim-1")  # type: ignore[arg-type]

    assert len(fake.calls) == 1
    assert "MATCH (c:Claim { claim_id: $claim_id })" in fake.calls[0].cypher
    assert "SUPPORTED_BY" in fake.calls[0].cypher
    assert fake.calls[0].parameters == {"claim_id": "claim-1"}

    assert len(evidence) == 2
    assert all(isinstance(e, Evidence) for e in evidence)
    assert [e.evidence_id for e in evidence] == ["ev-1", "ev-2"]


def test_get_policy_beneficiaries_groups_by_entity() -> None:
    records = [
        {"entity": _entity_dict("ent-1", "Acme"), "claim_id": "claim-1"},
        {"entity": _entity_dict("ent-1", "Acme"), "claim_id": "claim-2"},
        {"entity": _entity_dict("ent-2", "Beta"), "claim_id": "claim-1"},
    ]
    fake = FakeNeo4jClient(results=records)

    exposures = get_policy_beneficiaries(fake, "CHIPS Act")  # type: ignore[arg-type]

    assert len(fake.calls) == 1
    assert "BENEFITS_FROM" in fake.calls[0].cypher
    assert fake.calls[0].parameters == {"policy_name": "CHIPS Act"}

    assert len(exposures) == 2
    assert all(isinstance(e, CompanyExposure) for e in exposures)
    by_id = {e.entity.entity_id: e for e in exposures}
    assert by_id["ent-1"].claims == ["claim-1", "claim-2"]
    assert by_id["ent-2"].claims == ["claim-1"]
    assert by_id["ent-1"].exposure_type == "policy"


def test_get_geopolitical_exposures_uses_region() -> None:
    records = [
        {"entity": _entity_dict("ent-1", "Acme"), "claim_id": "claim-7"},
    ]
    fake = FakeNeo4jClient(results=records)

    exposures = get_geopolitical_exposures(fake, "Middle East")  # type: ignore[arg-type]

    assert fake.calls[0].parameters == {"region": "Middle East"}
    assert "EXPOSED_TO" in fake.calls[0].cypher
    assert exposures[0].exposure_type == "geopolitical"
    assert exposures[0].claims == ["claim-7"]
