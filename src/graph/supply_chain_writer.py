"""Neo4j writer for v18 product supply chain graphs."""

from __future__ import annotations

import json
from typing import Any

from src.graph.supply_chain_queries import (
    node_type_to_label,
    relation_type_to_cypher,
)
from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    SupplyChainEdge,
    SupplyChainNode,
)


class SupplyChainGraphWriter:
    """Persist v18 supply-chain nodes, edges, and evidence to Neo4j.

    The client is duck-typed. It can be either the project
    ``Neo4jClient`` with ``run(cypher, params)`` or a native Neo4j
    driver-like object with ``session().run(cypher, **params)``.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def write_graph(
        self,
        *,
        nodes: list[SupplyChainNode],
        edges: list[SupplyChainEdge],
        evidence: list[NormalizedSupplyChainEvidence],
    ) -> None:
        for ev in evidence:
            self.write_evidence(ev)
        for node in nodes:
            self.write_node(node)
        for edge in edges:
            self.write_edge(edge)

    def write_node(self, node: SupplyChainNode) -> None:
        label = node_type_to_label(node.node_type)
        cypher = (
            f"MERGE (n:{label} {{ entity_id: $entity_id }})\n"
            "SET n += $props"
        )
        self._run(
            cypher,
            {
                "entity_id": node.node_id,
                "props": {
                    "entity_id": node.node_id,
                    "label": node.label,
                    "name": node.normalized_name,
                    "ticker": node.ticker,
                    "depth": node.depth,
                    "parent_node_id": node.parent_node_id,
                    "confidence": node.confidence,
                    "evidence_ids": list(node.evidence_ids),
                    "metadata": dict(node.metadata),
                },
            },
        )

    def write_evidence(self, evidence: NormalizedSupplyChainEvidence) -> None:
        cypher = (
            "MERGE (e:Evidence { entity_id: $entity_id })\n"
            "SET e += $props"
        )
        self._run(
            cypher,
            {
                "entity_id": evidence.evidence_id,
                "props": _neo4j_props(evidence.model_dump(mode="json")),
            },
        )

    def write_edge(self, edge: SupplyChainEdge) -> None:
        rel_type = relation_type_to_cypher(edge.relation_type)
        cypher = (
            "MATCH (s { entity_id: $source_id })\n"
            "MATCH (t { entity_id: $target_id })\n"
            f"MERGE (s)-[r:{rel_type} {{ relation_id: $relation_id }}]->(t)\n"
            "SET r += $props"
        )
        self._run(
            cypher,
            {
                "source_id": edge.source_node_id,
                "target_id": edge.target_node_id,
                "relation_id": edge.edge_id,
                "props": {
                    "relation_id": edge.edge_id,
                    "confidence": edge.confidence,
                    "evidence_ids": list(edge.evidence_ids),
                    "value": edge.value,
                    "value_meaning": edge.value_meaning,
                    "metadata": dict(edge.metadata),
                },
            },
        )

    def _run(self, cypher: str, params: dict[str, Any]) -> None:
        if hasattr(self._client, "run"):
            self._client.run(cypher, _neo4j_params(params))
            return
        with self._client.session() as session:
            session.run(cypher, **_neo4j_params(params))


Primitive = str | int | float | bool | None


def _neo4j_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _neo4j_props(value) if isinstance(value, dict) else _neo4j_value(value)
        for key, value in params.items()
    }


def _neo4j_props(props: dict[str, Any]) -> dict[str, Any]:
    return {key: _neo4j_value(value) for key, value in props.items()}


def _neo4j_value(value: Any) -> Primitive | list[Primitive]:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        values = list(value)
        if all(
            item is None or isinstance(item, str | int | float | bool)
            for item in values
        ):
            return values
        return json.dumps(values, sort_keys=True)
    return json.dumps(value, sort_keys=True)


__all__ = ["SupplyChainGraphWriter"]
