"""Read-only Cypher queries against the supply chain graph.

The functions in this module are pure data-access: they take a
``Neo4jClient`` and return Pydantic models. The client is responsible
for actually executing the Cypher and returning record dicts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from src.graph.client import Neo4jClient
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence


class GraphPath(BaseModel):
    """A simple node/edge summary returned by traversal queries."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[Entity]
    relations: list[str]


class CompanyExposure(BaseModel):
    """A company along with a typed exposure (policy / geopolitical)."""

    model_config = ConfigDict(extra="forbid")

    entity: Entity
    exposure_type: str
    score: float
    claims: list[str]


def _coerce_dict(record: Any) -> dict[str, Any]:
    """Coerce a Neo4j node/record into a plain ``dict``.

    Real Neo4j nodes support ``dict(node)`` but the fake test doubles
    (SimpleNamespace) don't, so we fall back to ``vars``.
    """
    if isinstance(record, dict):
        return dict(record)
    if hasattr(record, "__dict__"):
        return dict(vars(record))
    raise TypeError(f"Cannot coerce {type(record).__name__} to dict")


def _entity_from_record(record: Any) -> Entity:
    """Build an Entity from a Neo4j record dict."""
    payload = _coerce_dict(record)
    payload.setdefault("evidence", [])
    return Entity.model_validate(payload)


def _evidence_from_record(record: Any) -> Evidence:
    """Build an Evidence from a Neo4j record dict."""
    payload = _coerce_dict(record)
    return Evidence.model_validate(payload)


def get_upstream_suppliers(
    client: Neo4jClient, ticker: str, depth: int = 2
) -> list[GraphPath]:
    """Return SUPPLIES_TO / BUYS_FROM paths leading *into* ``ticker``."""
    cypher = (
        "MATCH (c:Company { ticker: $ticker })\n"
        "MATCH p=(supplier)-[:SUPPLIES_TO|BUYS_FROM*1.."
        f"{depth}]->(c)\n"
        "RETURN p"
    )
    records = client.run(cypher, {"ticker": ticker})
    paths: list[GraphPath] = []
    for record in records:
        raw_path = record.get("p")
        if raw_path is None:
            continue
        nodes = [_entity_from_record(node) for node in raw_path.nodes]
        relations = [rel.type for rel in raw_path.relationships]
        paths.append(GraphPath(nodes=nodes, relations=relations))
    return paths


def get_downstream_customers(
    client: Neo4jClient, ticker: str, depth: int = 2
) -> list[GraphPath]:
    """Return paths leading *out of* ``ticker`` to its customers."""
    cypher = (
        "MATCH (c:Company { ticker: $ticker })\n"
        "MATCH p=(c)-[:SUPPLIES_TO|BUYS_FROM|CUSTOMER_OF*1.."
        f"{depth}]->(customer)\n"
        "RETURN p"
    )
    records = client.run(cypher, {"ticker": ticker})
    paths: list[GraphPath] = []
    for record in records:
        raw_path = record.get("p")
        if raw_path is None:
            continue
        nodes = [_entity_from_record(node) for node in raw_path.nodes]
        relations = [rel.type for rel in raw_path.relationships]
        paths.append(GraphPath(nodes=nodes, relations=relations))
    return paths


def get_policy_beneficiaries(
    client: Neo4jClient, policy_name: str
) -> list[CompanyExposure]:
    """Return companies that BENEFITS_FROM a policy matched by name."""
    cypher = (
        "MATCH (p:Policy { name: $policy_name })<-[:BENEFITS_FROM]-(c:Company)\n"
        "OPTIONAL MATCH (claim:Claim)-[:SUPPORTED_BY]->(:Evidence)\n"
        "WHERE claim.entity_ids CONTAINS c.entity_id\n"
        "RETURN c AS entity, claim.claim_id AS claim_id"
    )
    records = client.run(cypher, {"policy_name": policy_name})
    return _group_exposures(records, exposure_type="policy")


def get_geopolitical_exposures(
    client: Neo4jClient, region: str
) -> list[CompanyExposure]:
    """Return companies ``EXPOSED_TO`` a region via a geopolitical lens."""
    cypher = (
        "MATCH (r:Region { name: $region })<-[:EXPOSED_TO]-(c:Company)\n"
        "OPTIONAL MATCH (claim:Claim)-[:SUPPORTED_BY]->(:Evidence)\n"
        "WHERE claim.entity_ids CONTAINS c.entity_id\n"
        "RETURN c AS entity, claim.claim_id AS claim_id"
    )
    records = client.run(cypher, {"region": region})
    return _group_exposures(records, exposure_type="geopolitical")


def get_claim_evidence(
    client: Neo4jClient, claim_id: str
) -> list[Evidence]:
    """Return every Evidence node that ``SUPPORTED_BY``-links to a claim."""
    cypher = (
        "MATCH (c:Claim { claim_id: $claim_id })-[:SUPPORTED_BY]->(e:Evidence)\n"
        "RETURN e"
    )
    records = client.run(cypher, {"claim_id": claim_id})
    return [_evidence_from_record(dict(record["e"])) for record in records]


def _group_exposures(
    records: list[dict], exposure_type: str
) -> list[CompanyExposure]:
    """Pivot (entity, claim_id) rows into one ``CompanyExposure`` per entity."""
    bucket: dict[str, CompanyExposure] = {}
    for record in records:
        entity = _entity_from_record(dict(record["entity"]))
        claim_id = record.get("claim_id")
        key = entity.entity_id
        if key not in bucket:
            bucket[key] = CompanyExposure(
                entity=entity,
                exposure_type=exposure_type,
                score=0.0,
                claims=[],
            )
        if claim_id and claim_id not in bucket[key].claims:
            bucket[key].claims.append(claim_id)
    return list(bucket.values())
