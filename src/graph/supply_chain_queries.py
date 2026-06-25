"""v18 supply-chain graph queries.

These functions wrap the existing ``src.graph.client.Neo4jClient``
with the v18 variable-length depth contract. The spec requires
``depth`` to be whitelisted to ``[1, 5]`` because the Cypher
``[*1..$depth]`` syntax requires a literal integer.

Each function is duck-typed: it accepts anything with a
``session()`` context manager that returns a session with a
``run(cypher, **params)`` method. Unit tests pass a MagicMock.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.supply_chain.models import (
    SupplyChainEdge,
    SupplyChainNode,
)

MIN_DEPTH = 1
MAX_DEPTH = 5
ALLOWED_REL_TYPES: tuple[str, ...] = (
    "REQUIRES",
    "SUPPLIED_BY",
    "MANUFACTURED_BY",
    "HOSTED_ON",
    "POWERED_BY",
    "ENABLED_BY",
    "DEPENDS_ON",
    "OFFERS",
    "SUPPORTED_BY",
)


@runtime_checkable
class Neo4jLike(Protocol):
    """Duck-typed subset of :class:`src.graph.client.Neo4jClient`."""

    def session(self) -> Any:
        ...


def _validate_depth(depth: int) -> int:
    if depth < MIN_DEPTH or depth > MAX_DEPTH:
        raise ValueError(
            f"depth must be in [{MIN_DEPTH}, {MAX_DEPTH}]; got {depth}"
        )
    return depth


def get_product_upstream_paths(
    client: Neo4jLike,
    product_node_id: str,
    *,
    depth: int = 3,
) -> list[dict[str, Any]]:
    """Return the upstream paths from ``product_node_id``.

    The result is a list of dicts with ``nodes`` / ``edges`` keys
    that the v18 Sankey builder can convert into a payload.
    """
    depth = _validate_depth(depth)
    cypher = (
        "MATCH p=(root {entity_id: $product_node_id})"
        "-[:REQUIRES|SUPPLIED_BY|MANUFACTURED_BY|HOSTED_ON|POWERED_BY|ENABLED_BY|DEPENDS_ON|SUPPORTED_BY|OFFERS*1.."
        f"{depth}"
        "]->(n) "
        "RETURN p"
    )
    paths: list[dict[str, Any]] = []
    with client.session() as session:
        result = session.run(cypher, product_node_id=product_node_id)
        for record in result:
            neo_path = record["p"]
            paths.append(_path_record_to_dict(neo_path))
    return paths


def get_node_expansion_context(
    client: Neo4jLike,
    node_id: str,
    *,
    depth: int = 2,
) -> dict[str, Any]:
    """Return the 1-hop neighbourhood of ``node_id`` for expansion."""
    depth = _validate_depth(depth)
    cypher = (
        "MATCH p=(root {entity_id: $node_id})"
        "-[:REQUIRES|SUPPLIED_BY|MANUFACTURED_BY|HOSTED_ON|POWERED_BY|ENABLED_BY|DEPENDS_ON|SUPPORTED_BY|OFFERS*1.."
        f"{depth}"
        "]-(:Node) "
        "RETURN p"
    )
    with client.session() as session:
        result = session.run(cypher, node_id=node_id)
        return [_path_record_to_dict(record["p"]) for record in result]


def _path_record_to_dict(neo_path: Any) -> dict[str, Any]:
    """Convert a Neo4j ``Path`` to a v18 path dict.

    The conversion is best-effort. Neo4j ``Path`` exposes
    ``nodes`` and ``relationships``; each node has
    ``element_id`` / ``labels`` / dict-like properties; each
    relationship has ``type`` and dict-like properties.
    """
    nodes: list[dict[str, Any]] = []
    for n in neo_path.nodes:
        nodes.append(
            {
                "node_id": str(
                    getattr(n, "element_id", None) or n["entity_id"]
                ),
                "node_type": n.labels[0] if n.labels else "unknown",
                "label": str(n.get("label") or n.get("name") or "node"),
                "normalized_name": str(n.get("name") or "node"),
                "ticker": n.get("ticker"),
                "depth": 0,
                "parent_node_id": None,
                "confidence": float(n.get("confidence", 0.5) or 0.5),
                "evidence_ids": list(n.get("evidence_ids", [])),
                "metadata": {},
            }
        )
    edges: list[dict[str, Any]] = []
    for rel in neo_path.relationships:
        edges.append(
            {
                "edge_id": str(
                    getattr(rel, "element_id", None) or rel["relation_id"]
                ),
                "source_node_id": str(rel.start_node["entity_id"]),
                "target_node_id": str(rel.end_node["entity_id"]),
                "relation_type": rel.type.lower(),
                "value": float(rel.get("value", 0.5) or 0.5),
                "value_meaning": "importance",
                "confidence": float(rel.get("confidence", 0.5) or 0.5),
                "evidence_ids": list(rel.get("evidence_ids", [])),
                "metadata": {},
            }
        )
    return {"nodes": nodes, "edges": edges}


def node_type_to_label(node_type: str) -> str:
    """Map a v18 ``NodeType`` to the corresponding Neo4j label."""
    mapping = {
        "company": "Company",
        "product": "Product",
        "component": "Component",
        "service": "Service",
        "commodity": "Commodity",
        "infrastructure": "Infrastructure",
        "energy": "EnergySource",
        "region": "Region",
        "unknown": "Unknown",
    }
    return mapping.get(node_type, "Unknown")


def relation_type_to_cypher(relation_type: str) -> str:
    """Map a v18 ``RelationType`` to its canonical Cypher verb."""
    mapping = {
        "requires": "REQUIRES",
        "supplied_by": "SUPPLIED_BY",
        "depends_on": "DEPENDS_ON",
        "manufactured_by": "MANUFACTURED_BY",
        "hosted_on": "HOSTED_ON",
        "powered_by": "POWERED_BY",
        "enabled_by": "ENABLED_BY",
        "hypothesized": "HYPOTHESIZED",
    }
    return mapping.get(relation_type, "RELATED_TO")


def node_from_neo4j_properties(
    entity_id: str,
    label: str,
    properties: dict[str, Any],
) -> SupplyChainNode:
    """Best-effort conversion of a Neo4j record to a v18 node."""
    return SupplyChainNode(
        node_id=entity_id,
        node_type=_label_to_node_type(label),
        label=str(properties.get("label") or label),
        normalized_name=str(properties.get("name") or label).lower(),
        ticker=properties.get("ticker"),
        depth=int(properties.get("depth", 0) or 0),
        parent_node_id=properties.get("parent_node_id"),
        confidence=float(properties.get("confidence", 0.5) or 0.5),
        evidence_ids=list(properties.get("evidence_ids", [])),
        metadata={},
    )


def edge_from_neo4j_relationship(
    rel_id: str,
    rel_type: str,
    src_id: str,
    tgt_id: str,
    properties: dict[str, Any],
) -> SupplyChainEdge:
    """Best-effort conversion of a Neo4j relationship to a v18 edge."""
    return SupplyChainEdge(
        edge_id=rel_id,
        source_node_id=src_id,
        target_node_id=tgt_id,
        relation_type=_cypher_to_relation_type(rel_type),
        value=float(properties.get("value", 0.5) or 0.5),
        value_meaning="importance",
        confidence=float(properties.get("confidence", 0.5) or 0.5),
        evidence_ids=list(properties.get("evidence_ids", [])),
        metadata={},
    )


def _label_to_node_type(label: str) -> str:
    mapping = {
        "Company": "company",
        "Product": "product",
        "Component": "component",
        "Service": "service",
        "Commodity": "commodity",
        "Infrastructure": "infrastructure",
        "EnergySource": "energy",
        "Region": "region",
    }
    return mapping.get(label, "unknown")


def _cypher_to_relation_type(cypher_type: str) -> str:
    mapping = {
        "REQUIRES": "requires",
        "SUPPLIED_BY": "supplied_by",
        "DEPENDS_ON": "depends_on",
        "MANUFACTURED_BY": "manufactured_by",
        "HOSTED_ON": "hosted_on",
        "POWERED_BY": "powered_by",
        "ENABLED_BY": "enabled_by",
        "HYPOTHESIZED": "hypothesized",
    }
    return mapping.get(cypher_type, "depends_on")


__all__ = [
    "ALLOWED_REL_TYPES",
    "MAX_DEPTH",
    "MIN_DEPTH",
    "edge_from_neo4j_relationship",
    "get_node_expansion_context",
    "get_product_upstream_paths",
    "node_from_neo4j_properties",
    "node_type_to_label",
    "relation_type_to_cypher",
]
