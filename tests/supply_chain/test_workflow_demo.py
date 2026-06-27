"""v18 tests for the demo workflow (OpenAI / ChatGPT)."""

from __future__ import annotations

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
    node_ids = {n.node_id for n in state.nodes}
    assert "product:chatgpt" in node_ids
    product = next(node for node in state.nodes if node.node_id == "product:chatgpt")
    assert product.parent_node_id == "company:openai"
    assert product.depth == 1
    # The spec requires the CPU / GPU / power branches.
    for required in (
        "component:cpu",
        "component:gpu-accelerator",
        "energy:datacenter-power",
    ):
        assert required in node_ids, f"missing {required} in workflow output"
        required_node = next(node for node in state.nodes if node.node_id == required)
        assert required_node.parent_node_id is not None
        parent = next(
            node for node in state.nodes if node.node_id == required_node.parent_node_id
        )
        assert required_node.depth > parent.depth


async def test_demo_workflow_sankey_payload_is_acyclic() -> None:
    state = await run_supply_chain_workflow(_request())
    assert state.sankey is not None
    adjacency: dict[str, list[str]] = {n.node_id: [] for n in state.sankey.nodes}
    for link in state.sankey.links:
        if link.relation_type != "hypothesized":
            adjacency[link.source_node_id].append(link.target_node_id)
    color: dict[str, int] = dict.fromkeys(adjacency, 0)

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
    assert state.evaluation.final_status in {"pass", "needs_review"}
    # All confirmed edges must have evidence.
    assert not state.evaluation.unsupported_edges


async def test_unknown_demo_product_is_needs_review_without_fixture_evidence() -> None:
    state = await run_supply_chain_workflow(
        SupplyChainExploreRequest(
            company_name="Apple",
            product_name="Iphone",
            max_depth=3,
            demo_mode=True,
            cached_mode=True,
        )
    )
    assert state.status == "needs_review"
    assert state.evaluation is not None
    assert state.evaluation.final_status == "needs_review"
    assert state.links == []
    assert state.evidence == []
    assert any("no demo fixture" in warning for warning in state.warnings)
