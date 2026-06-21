"""Graph algorithms exposed over the Cypher layer.

We deliberately avoid pulling in Neo4j GDS for the first cut. Once the
graph grows we can promote community detection and link prediction to
real algorithms.
"""

from __future__ import annotations

from src.graph.client import Neo4jClient


def degree_centrality(
    client: Neo4jClient, label: str = "Company"
) -> dict[str, float]:
    """Return ``{entity_id: degree}`` for every node of ``label``."""
    cypher = (
        f"MATCH (n:{label})\n"
        "OPTIONAL MATCH (n)-[r]-()\n"
        "WITH n, count(r) AS degree\n"
        "RETURN n.entity_id AS entity_id, degree"
    )
    records = client.run(cypher)
    return {record["entity_id"]: float(record["degree"]) for record in records}


def shortest_path(
    client: Neo4jClient, source_id: str, target_id: str, max_depth: int = 4
) -> list[str]:
    """Return the entity_ids along the shortest undirected path.

    Returns an empty list when no path exists within ``max_depth``.
    """
    cypher = (
        "MATCH (s { entity_id: $source_id }), (t { entity_id: $target_id })\n"
        f"MATCH p=shortestPath((s)-[*..{max_depth}]-(t))\n"
        "RETURN [n IN nodes(p) | n.entity_id] AS path"
    )
    records = client.run(
        cypher, {"source_id": source_id, "target_id": target_id}
    )
    if not records:
        return []
    return [str(node_id) for node_id in records[0].get("path", [])]


# ---------------------------------------------------------------------------
# TODO(neo4j-gds):
#   - community detection via Louvain / Label Propagation once GDS is on the
#     classpath. Run ``CALL gds.louvain.stream(...)`` and surface the result.
#   - link prediction using Adamic-Adar or GDS ``linkPrediction`` pipelines.
#   - PageRank over the Company graph to identify systemic suppliers.
# ---------------------------------------------------------------------------
