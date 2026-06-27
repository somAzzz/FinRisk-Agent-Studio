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
    SupplyChainExploreState,
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

    def write_projection(self, state: SupplyChainExploreState) -> None:
        """Persist the final Sankey artifact with run context.

        The run store remains the source of truth for exact UI replay.
        Neo4j receives this projection for cross-run graph queries.
        """
        if state.sankey is None:
            return
        self.write_run(state)
        for ev in state.sankey.evidence:
            self.write_evidence(ev)
            self.write_run_evidence(state.run_id, ev.evidence_id)
        for node in state.sankey.nodes:
            self.write_node(node, run_id=state.run_id)
            self.write_run_node(state.run_id, node.node_id)
        for edge in state.sankey.links:
            self.write_edge(edge, run_id=state.run_id)
            self.write_run_edge(state.run_id, edge.edge_id)

    def write_run(self, state: SupplyChainExploreState) -> None:
        cypher = (
            "MERGE (r:SupplyChainRun { run_id: $run_id })\n"
            "SET r += $props"
        )
        self._run(
            cypher,
            {
                "run_id": state.run_id,
                "props": {
                    "run_id": state.run_id,
                    "status": state.status,
                    "company_name": state.request.company_name,
                    "ticker": state.request.ticker,
                    "product_name": state.request.product_name,
                    "created_at": state.created_at.isoformat(),
                    "node_count": len(state.sankey.nodes) if state.sankey else 0,
                    "link_count": len(state.sankey.links) if state.sankey else 0,
                    "evidence_count": len(state.sankey.evidence) if state.sankey else 0,
                    "evaluation": (
                        state.evaluation.model_dump(mode="json")
                        if state.evaluation
                        else None
                    ),
                },
            },
        )

    def write_node(self, node: SupplyChainNode, *, run_id: str | None = None) -> None:
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
                    "last_run_id": run_id,
                    "metadata": dict(node.metadata),
                    "profile": dict(node.metadata.get("profile", {}))
                    if isinstance(node.metadata.get("profile"), dict)
                    else None,
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

    def write_edge(self, edge: SupplyChainEdge, *, run_id: str | None = None) -> None:
        rel_type = relation_type_to_cypher(edge.relation_type)
        props = {
            "relation_id": edge.edge_id,
            "confidence": edge.confidence,
            "evidence_ids": list(edge.evidence_ids),
            "value": edge.value,
            "value_meaning": edge.value_meaning,
            "run_id": run_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
            "metadata": dict(edge.metadata),
        }
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
                "props": props,
            },
        )
        self._run(
            (
                "MERGE (edge:SupplyChainEdge { relation_id: $relation_id })\n"
                "SET edge += $props"
            ),
            {"relation_id": edge.edge_id, "props": props},
        )

    def write_run_node(self, run_id: str, node_id: str) -> None:
        self._run(
            (
                "MATCH (r:SupplyChainRun { run_id: $run_id })\n"
                "MATCH (n { entity_id: $node_id })\n"
                "MERGE (r)-[:CONTAINS_NODE]->(n)"
            ),
            {"run_id": run_id, "node_id": node_id},
        )

    def write_run_edge(self, run_id: str, edge_id: str) -> None:
        self._run(
            (
                "MATCH (r:SupplyChainRun { run_id: $run_id })\n"
                "MATCH (e:SupplyChainEdge { relation_id: $edge_id })\n"
                "MERGE (r)-[:CONTAINS_EDGE]->(e)"
            ),
            {"run_id": run_id, "edge_id": edge_id},
        )

    def write_run_evidence(self, run_id: str, evidence_id: str) -> None:
        self._run(
            (
                "MATCH (r:SupplyChainRun { run_id: $run_id })\n"
                "MATCH (e:Evidence { entity_id: $evidence_id })\n"
                "MERGE (r)-[:CONTAINS_EVIDENCE]->(e)"
            ),
            {"run_id": run_id, "evidence_id": evidence_id},
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
