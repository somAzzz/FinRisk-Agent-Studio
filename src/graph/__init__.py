"""Neo4j-backed supply chain graph layer.

Re-exports the public client, writer, query, and algorithm surface
so callers can simply do ``from src.graph import Neo4jClient,
GraphWriter, get_upstream_suppliers``.
"""

from __future__ import annotations

from src.graph.algorithms import degree_centrality, shortest_path
from src.graph.client import Neo4jClient
from src.graph.queries import (
    CompanyExposure,
    GraphPath,
    get_claim_evidence,
    get_downstream_customers,
    get_geopolitical_exposures,
    get_policy_beneficiaries,
    get_upstream_suppliers,
)
from src.graph.writer import GraphWriter

__all__ = [
    "CompanyExposure",
    "GraphPath",
    "GraphWriter",
    "Neo4jClient",
    "degree_centrality",
    "get_claim_evidence",
    "get_downstream_customers",
    "get_geopolitical_exposures",
    "get_policy_beneficiaries",
    "get_upstream_suppliers",
    "shortest_path",
]
