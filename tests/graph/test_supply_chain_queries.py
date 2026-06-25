"""v18 tests for the Neo4j graph query layer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.graph.supply_chain_queries import (
    get_node_expansion_context,
    get_product_upstream_paths,
    node_from_neo4j_properties,
    node_type_to_label,
    relation_type_to_cypher,
)


def _neo4j_path_with_nodes(n=2):
    n1 = MagicMock()
    n1.element_id = "n1"
    n1.labels = ["Company"]
    n1.__getitem__ = lambda self, key: {"label": "Apple", "name": "apple"}.get(key)
    n1.get = lambda key, default=None: {"label": "Apple", "name": "apple"}.get(
        key, default
    )

    n2 = MagicMock()
    n2.element_id = "n2"
    n2.labels = ["Component"]
    n2.__getitem__ = lambda self, key: {"label": "GPU", "name": "gpu"}.get(key)
    n2.get = lambda key, default=None: {"label": "GPU", "name": "gpu"}.get(
        key, default
    )

    rel = MagicMock()
    rel.element_id = "r1"
    rel.type = "REQUIRES"
    rel.start_node = n1
    rel.end_node = n2
    rel.__getitem__ = lambda self, key: {
        "relation_id": "r1",
        "value": 0.5,
        "confidence": 0.7,
        "evidence_ids": ["ev-1"],
    }.get(key)
    rel.get = lambda key, default=None: {
        "relation_id": "r1",
        "value": 0.5,
        "confidence": 0.7,
        "evidence_ids": ["ev-1"],
    }.get(key, default)

    path = MagicMock()
    path.nodes = [n1, n2][:n]
    path.relationships = [rel][: n - 1] if n > 1 else []
    return path


def test_depth_validation_rejects_out_of_range() -> None:
    client = MagicMock()
    with pytest.raises(ValueError):
        get_product_upstream_paths(client, "product:chatgpt", depth=0)
    with pytest.raises(ValueError):
        get_product_upstream_paths(client, "product:chatgpt", depth=6)


def test_get_product_upstream_paths_returns_records() -> None:
    record = MagicMock()
    record.__getitem__ = lambda self, key: _neo4j_path_with_nodes(2)
    session = MagicMock()
    session.run.return_value = [record]
    client = MagicMock()
    client.session.return_value.__enter__.return_value = session

    paths = get_product_upstream_paths(client, "product:chatgpt", depth=3)
    assert paths
    assert paths[0]["nodes"]
    # Cypher template uses a literal depth (whitelist enforcement).
    cypher = session.run.call_args[0][0]
    assert "depth: 3" not in cypher  # no parameter binding for depth
    assert "1..3" in cypher  # literal depth is interpolated


def test_get_node_expansion_context() -> None:
    record = MagicMock()
    record.__getitem__ = lambda self, key: _neo4j_path_with_nodes(2)
    session = MagicMock()
    session.run.return_value = [record]
    client = MagicMock()
    client.session.return_value.__enter__.return_value = session
    result = get_node_expansion_context(client, "component:cpu", depth=2)
    assert result
    # Depth must be interpolated into the cypher string.
    cypher = session.run.call_args[0][0]
    assert "1..2" in cypher


def test_node_type_to_label_mapping() -> None:
    assert node_type_to_label("company") == "Company"
    assert node_type_to_label("component") == "Component"
    assert node_type_to_label("energy") == "EnergySource"
    assert node_type_to_label("unknown") == "Unknown"


def test_relation_type_to_cypher_mapping() -> None:
    assert relation_type_to_cypher("requires") == "REQUIRES"
    assert relation_type_to_cypher("supplied_by") == "SUPPLIED_BY"
    assert relation_type_to_cypher("hypothesized") == "HYPOTHESIZED"


def test_node_from_neo4j_properties_round_trip() -> None:
    node = node_from_neo4j_properties(
        "company:apple",
        "Company",
        {"label": "Apple", "name": "apple", "ticker": "AAPL", "confidence": 0.9},
    )
    assert node.node_id == "company:apple"
    assert node.node_type == "company"
    assert node.ticker == "AAPL"
    assert node.confidence == 0.9


def test_get_product_upstream_paths_propagates_session_error() -> None:
    client = MagicMock()
    client.session.return_value.__enter__.side_effect = RuntimeError("neo4j down")
    with pytest.raises(RuntimeError):
        get_product_upstream_paths(client, "product:chatgpt", depth=3)
