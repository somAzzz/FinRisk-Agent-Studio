"""v18 tests for the demo workflow (OpenAI / ChatGPT)."""

from __future__ import annotations

import asyncio

import pytest

from src.supply_chain.models import SupplyChainExploreRequest
from src.supply_chain.workflow import run_supply_chain_workflow


def _request() -> SupplyChainExploreRequest:
    return SupplyChainExploreRequest(
        company_name="OpenAI",
        product_name="ChatGPT",
        max_depth=3,
        demo_mode=True,
        cached_mode=True,
    )


async def test_demo_workflow_completes() -> None:
    state = await run_supply_chain_workflow(_request())
    assert state.status == "completed"
    assert state.run_id.startswith("sc-run-")
    assert state.sankey is not None


async def test_demo_workflow_produces_expected_artefacts() -> None:
    state = await run_supply_chain_workflow(_request())
    assert len(state.nodes) > 0
    assert len(state.links) > 0
    assert len(state.evidence) > 0
    # The root product is product:chatgpt.
    node_ids = {n.node_id for n in state.nodes}
    assert "product:chatgpt" in node_ids
    # The spec requires the CPU / GPU / power branches.
    for required in (
        "component:cpu",
        "component:gpu-accelerator",
        "energy:datacenter-power",
    ):
        assert required in node_ids, f"missing {required} in workflow output"


async def test_demo_workflow_sankey_payload_is_acyclic() -> None:
    state = await run_supply_chain_workflow(_request())
    assert state.sankey is not None
    adjacency: dict[str, list[str]] = {n.node_id: [] for n in state.sankey.nodes}
    for link in state.sankey.links:
        if link.relation_type != "hypothesized":
            adjacency[link.source_node_id].append(link.target_node_id)
    color: dict[str, int] = {n: 0 for n in adjacency}

    def dfs(node: str) -> bool:
        color[node] = 1
        for nxt in adjacency[node]:
            if color[nxt] == 1:
                return True
            if color[nxt] == 0 and dfs(nxt):
                return True
        color[node] = 2
        return False

    assert not any(color[n] == 0 and dfs(n) for n in adjacency)


async def test_demo_workflow_evaluation_passes() -> None:
    state = await run_supply_chain_workflow(_request())
    assert state.evaluation is not None
    assert state.evaluation.final_status in {"completed", "needs_review"}
    # All confirmed edges must have evidence.
    assert not state.evaluation.unsupported_edges
