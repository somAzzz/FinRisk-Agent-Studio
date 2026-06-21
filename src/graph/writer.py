"""Write extracted entities, relations, claims, and evidence to Neo4j.

All write paths use ``MERGE`` on a label-specific id property so that
re-running the writer is idempotent.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.graph.client import Neo4jClient
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation

logger = logging.getLogger(__name__)


# Map EntityType snake_case values to the matching Neo4j label.
_ENTITY_TYPE_TO_LABEL: dict[str, str] = {
    "company": "Company",
    "product": "Product",
    "segment": "Segment",
    "customer": "Customer",
    "supplier": "Supplier",
    "competitor": "Competitor",
    "country": "Country",
    "region": "Region",
    "commodity": "Commodity",
    "policy": "Policy",
    "risk": "Risk",
    "opportunity": "Opportunity",
    "executive": "Executive",
    "event": "Event",
}


def _label_for(entity: Entity) -> str:
    try:
        return _ENTITY_TYPE_TO_LABEL[entity.entity_type]
    except KeyError as exc:
        msg = f"Unknown entity_type for graph write: {entity.entity_type!r}"
        raise ValueError(msg) from exc


def _entity_props(entity: Entity) -> dict[str, Any]:
    """Project an Entity into a flat dict of Neo4j node properties."""
    return {
        "entity_id": entity.entity_id,
        "name": entity.name,
        "normalized_name": entity.normalized_name,
        "ticker": entity.ticker,
        "cik": entity.cik,
        "aliases": list(entity.aliases),
        "metadata": dict(entity.metadata),
        "confidence": entity.confidence,
    }


def _evidence_props(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_type": evidence.source_type,
        "source_id": evidence.source_id,
        "title": evidence.title,
        "url": evidence.url,
        "section": evidence.section,
        "speaker": evidence.speaker,
        "quote": evidence.quote,
        "retrieved_at": (
            evidence.retrieved_at.isoformat() if evidence.retrieved_at else None
        ),
        "published_at": (
            evidence.published_at.isoformat() if evidence.published_at else None
        ),
        "char_start": evidence.char_start,
        "char_end": evidence.char_end,
        "confidence": evidence.confidence,
        "metadata": dict(evidence.metadata),
    }


def _claim_props(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "claim_type": claim.claim_type,
        "statement": claim.statement,
        "confidence": claim.confidence,
        "metadata": dict(claim.metadata),
        "entity_ids": [e.entity_id for e in claim.entities],
        "relation_ids": [r.relation_id for r in claim.relations],
    }


class _ResultLike(Protocol):
    """Duck-typed shape expected by ``write_extraction_result``."""

    entities: list[Entity]
    relations: list[Relation]
    claims: list[Claim]
    evidence: list[Evidence]


class GraphWriter:
    """Persist the Step 07 extraction output into Neo4j."""

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    # -- public write API --------------------------------------------------
    def write_entity(self, entity: Entity) -> None:
        label = _label_for(entity)
        cypher = (
            f"MERGE (n:{label} {{ {label.lower()}_id: $entity_id }})\n"
            "SET n += $props"
        )
        self._client.run(
            cypher,
            {"entity_id": entity.entity_id, "props": _entity_props(entity)},
        )

    def write_evidence(self, evidence: Evidence) -> None:
        cypher = (
            "MERGE (n:Evidence { evidence_id: $evidence_id })\n"
            "SET n += $props"
        )
        self._client.run(
            cypher,
            {
                "evidence_id": evidence.evidence_id,
                "props": _evidence_props(evidence),
            },
        )

    def write_relation(self, relation: Relation) -> None:
        # Ensure both endpoints exist (idempotent MERGE on their natural key)
        # before merging the typed relationship between them.
        for endpoint in (relation.source, relation.target):
            self.write_entity(endpoint)

        cypher = (
            "MATCH (s { entity_id: $source_id })\n"
            "MATCH (t { entity_id: $target_id })\n"
            f"MERGE (s)-[r:{_rel_type(relation.relation_type)} "
            "{ relation_id: $relation_id }]->(t)\n"
            "SET r += $props"
        )
        self._client.run(
            cypher,
            {
                "source_id": relation.source.entity_id,
                "target_id": relation.target.entity_id,
                "relation_id": relation.relation_id,
                "props": {
                    "relation_id": relation.relation_id,
                    "confidence": relation.confidence,
                    "metadata": dict(relation.metadata),
                },
            },
        )

    def write_claim(self, claim: Claim) -> None:
        cypher = (
            "MERGE (c:Claim { claim_id: $claim_id })\n"
            "SET c += $props"
        )
        self._client.run(
            cypher, {"claim_id": claim.claim_id, "props": _claim_props(claim)}
        )

        if not claim.evidence:
            logger.warning(
                "Claim %s has no evidence; skipping SUPPORTED_BY links.",
                claim.claim_id,
            )
            return

        # Make sure every evidence node exists, then link the claim.
        for ev in claim.evidence:
            self.write_evidence(ev)

        link_cypher = (
            "MATCH (c:Claim { claim_id: $claim_id })\n"
            "MATCH (e:Evidence { evidence_id: $evidence_id })\n"
            "MERGE (c)-[:SUPPORTED_BY]->(e)"
        )
        for ev in claim.evidence:
            self._client.run(
                link_cypher,
                {"claim_id": claim.claim_id, "evidence_id": ev.evidence_id},
            )

    def write_extraction_result(self, result: _ResultLike) -> None:
        """Best-effort bulk write of a Step 07 extraction result.

        Order matters: evidence and entities must exist before relations
        and claims reference them.
        """
        for ev in result.evidence:
            self.write_evidence(ev)
        for entity in result.entities:
            self.write_entity(entity)
        for relation in result.relations:
            self.write_relation(relation)
        for claim in result.claims:
            self.write_claim(claim)


# -- helpers -----------------------------------------------------------------


def _rel_type(relation_type: str) -> str:
    """Translate the snake_case ``relation_type`` to UPPER_SNAKE Cypher label."""
    return relation_type.upper()
