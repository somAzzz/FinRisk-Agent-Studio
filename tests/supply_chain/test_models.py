"""v18 tests for the supply chain Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.supply_chain.fixtures import build_default_fixture
from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    SankeyPayload,
    SupplyChainEdge,
    SupplyChainExpandRequest,
    SupplyChainExploreRequest,
    SupplyChainNode,
)
from src.workflows.state import utcnow

# ---------------------------------------------------------------------------
# SupplyChainExploreRequest
# ---------------------------------------------------------------------------


def test_request_requires_product_name() -> None:
    with pytest.raises(ValidationError):
        SupplyChainExploreRequest.model_validate(
            {"company_name": "OpenAI", "product_name": ""}
        )


def test_request_requires_company_or_ticker() -> None:
    with pytest.raises(ValidationError):
        SupplyChainExploreRequest.model_validate(
            {"product_name": "ChatGPT"}
        )


def test_request_max_depth_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SupplyChainExploreRequest.model_validate(
            {
                "company_name": "OpenAI",
                "product_name": "ChatGPT",
                "max_depth": 6,
            }
        )


def test_request_accepts_minimal_payload() -> None:
    req = SupplyChainExploreRequest.model_validate(
        {"company_name": "OpenAI", "product_name": "ChatGPT"}
    )
    assert req.max_depth == 3
    assert req.max_suppliers_per_node == 5
    assert req.demo_mode is False


# ---------------------------------------------------------------------------
# SupplyChainExpandRequest
# ---------------------------------------------------------------------------


def test_expand_request_requires_node_id() -> None:
    with pytest.raises(ValidationError):
        SupplyChainExpandRequest.model_validate(
            {"parent_run_id": "r1", "node_id": ""}
        )


def test_expand_request_rejects_depth_above_4() -> None:
    with pytest.raises(ValidationError):
        SupplyChainExpandRequest.model_validate(
            {
                "parent_run_id": "r1",
                "node_id": "component:cpu",
                "max_depth": 5,
            }
        )


# ---------------------------------------------------------------------------
# SupplyChainNode / Edge
# ---------------------------------------------------------------------------


def test_node_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        SupplyChainNode.model_validate(
            {
                "node_id": "company:openai",
                "node_type": "company",
                "label": "OpenAI",
                "normalized_name": "openai",
                "depth": 0,
                "confidence": 1.5,
            }
        )


def test_edge_rejects_negative_value() -> None:
    with pytest.raises(ValidationError):
        SupplyChainEdge.model_validate(
            {
                "edge_id": "e-1",
                "source_node_id": "a",
                "target_node_id": "b",
                "relation_type": "supplied_by",
                "value": -0.1,
                "confidence": 0.5,
                "evidence_ids": ["ev-1"],
            }
        )


def test_confirmed_edge_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        SupplyChainEdge.model_validate(
            {
                "edge_id": "e-2",
                "source_node_id": "a",
                "target_node_id": "b",
                "relation_type": "supplied_by",
                "value": 0.5,
                "confidence": 0.5,
                "evidence_ids": [],
            }
        )


def test_hypothesised_edge_may_omit_evidence() -> None:
    edge = SupplyChainEdge.model_validate(
        {
            "edge_id": "e-3",
            "source_node_id": "a",
            "target_node_id": "b",
            "relation_type": "hypothesized",
            "value": 0.0,
            "confidence": 0.2,
            "evidence_ids": [],
            "metadata": {"reason": "no direct evidence yet"},
        }
    )
    assert edge.relation_type == "hypothesized"


def test_edge_rejects_self_loop() -> None:
    with pytest.raises(ValidationError):
        SupplyChainEdge.model_validate(
            {
                "edge_id": "e-loop",
                "source_node_id": "a",
                "target_node_id": "a",
                "relation_type": "supplied_by",
                "value": 0.1,
                "confidence": 0.5,
                "evidence_ids": ["ev-1"],
            }
        )


# ---------------------------------------------------------------------------
# NormalizedSupplyChainEvidence
# ---------------------------------------------------------------------------


def test_evidence_rejects_invalid_source_type() -> None:
    with pytest.raises(ValidationError):
        NormalizedSupplyChainEvidence.model_validate(
            {
                "evidence_id": "ev-1",
                "source_type": "blog",  # not in the allowed list
                "quote": "x",
                "summary": "y",
                "retrieved_at": utcnow(),
                "confidence": 0.5,
            }
        )


# ---------------------------------------------------------------------------
# SankeyPayload
# ---------------------------------------------------------------------------


def test_sankey_payload_rejects_link_to_unknown_node() -> None:
    with pytest.raises(ValidationError):
        SankeyPayload.model_validate(
            {
                "nodes": [
                    {
                        "node_id": "a",
                        "node_type": "company",
                        "label": "A",
                        "normalized_name": "a",
                        "depth": 0,
                        "confidence": 0.9,
                    }
                ],
                "links": [
                    {
                        "edge_id": "e-1",
                        "source_node_id": "a",
                        "target_node_id": "missing",
                        "relation_type": "supplied_by",
                        "value": 0.5,
                        "confidence": 0.5,
                        "evidence_ids": ["ev-1"],
                    }
                ],
                "evidence": [],
                "warnings": [],
            }
        )


def test_sankey_payload_rejects_self_loop() -> None:
    with pytest.raises(ValidationError):
        SankeyPayload.model_validate(
            {
                "nodes": [
                    {
                        "node_id": "a",
                        "node_type": "company",
                        "label": "A",
                        "normalized_name": "a",
                        "depth": 0,
                        "confidence": 0.9,
                    }
                ],
                "links": [
                    {
                        "edge_id": "e-loop",
                        "source_node_id": "a",
                        "target_node_id": "a",
                        "relation_type": "supplied_by",
                        "value": 0.1,
                        "confidence": 0.5,
                        "evidence_ids": ["ev-1"],
                    }
                ],
                "evidence": [],
                "warnings": [],
            }
        )


def test_sankey_payload_rejects_confirmed_cycle() -> None:
    with pytest.raises(ValidationError):
        # a -> b -> a
        SankeyPayload.model_validate(
            {
                "nodes": [
                    {
                        "node_id": "a",
                        "node_type": "company",
                        "label": "A",
                        "normalized_name": "a",
                        "depth": 0,
                        "confidence": 0.9,
                    },
                    {
                        "node_id": "b",
                        "node_type": "company",
                        "label": "B",
                        "normalized_name": "b",
                        "depth": 0,
                        "confidence": 0.9,
                    },
                ],
                "links": [
                    {
                        "edge_id": "e-1",
                        "source_node_id": "a",
                        "target_node_id": "b",
                        "relation_type": "supplied_by",
                        "value": 0.1,
                        "confidence": 0.5,
                        "evidence_ids": ["ev-1"],
                    },
                    {
                        "edge_id": "e-2",
                        "source_node_id": "b",
                        "target_node_id": "a",
                        "relation_type": "supplied_by",
                        "value": 0.1,
                        "confidence": 0.5,
                        "evidence_ids": ["ev-2"],
                    },
                ],
                "evidence": [],
                "warnings": [],
            }
        )


# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------


def test_default_fixture_loads_and_validates() -> None:
    fixture = build_default_fixture()
    # request parses
    SupplyChainExploreRequest.model_validate(fixture["request"])
    # every node parses
    for raw in fixture["nodes"]:
        SupplyChainNode.model_validate(raw)
    # every link parses
    for raw in fixture["links"]:
        SupplyChainEdge.model_validate(raw)
    # evidence parses
    for raw in fixture["evidence"]:
        NormalizedSupplyChainEvidence.model_validate(raw)
    # sankey parses
    SankeyPayload.model_validate(fixture["sankey"])


def test_default_fixture_has_required_nodes() -> None:
    fixture = build_default_fixture()
    node_ids = {n["node_id"] for n in fixture["nodes"]}
    required = {
        "product:chatgpt",
        "service:cloud-compute",
        "company:microsoft",
        "company:oracle",
        "company:coreweave",
        "component:gpu-accelerator",
        "company:nvidia",
        "component:cpu",
        "company:amd",
        "company:intel",
        "component:hbm-memory",
        "company:sk-hynix",
        "company:samsung",
        "company:micron",
        "component:networking",
        "company:broadcom",
        "company:arista",
        "energy:datacenter-power",
    }
    missing = required - node_ids
    assert not missing, f"missing fixture nodes: {missing}"


def test_default_fixture_has_required_edges() -> None:
    fixture = build_default_fixture()
    edge_pairs = {(e["source_node_id"], e["target_node_id"]) for e in fixture["links"]}
    required = {
        ("product:chatgpt", "service:cloud-compute"),
        ("service:cloud-compute", "company:microsoft"),
        ("service:cloud-compute", "company:oracle"),
        ("service:cloud-compute", "company:coreweave"),
        ("service:cloud-compute", "component:gpu-accelerator"),
        ("component:gpu-accelerator", "company:nvidia"),
        ("service:cloud-compute", "component:cpu"),
        ("component:cpu", "company:amd"),
        ("component:cpu", "company:intel"),
        ("component:gpu-accelerator", "component:hbm-memory"),
        ("component:hbm-memory", "company:sk-hynix"),
        ("component:hbm-memory", "company:samsung"),
        ("component:hbm-memory", "company:micron"),
        ("service:cloud-compute", "component:networking"),
        ("component:networking", "company:broadcom"),
        ("component:networking", "company:arista"),
        ("service:cloud-compute", "energy:datacenter-power"),
    }
    missing = required - edge_pairs
    assert not missing, f"missing fixture edges: {missing}"
