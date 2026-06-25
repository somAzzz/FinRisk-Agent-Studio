"""v18 tests for recursive expansion of an existing supply chain run."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.supply_chain.models import SupplyChainExploreRequest
from src.supply_chain.workflow import (
    expand_supply_chain_workflow,
    run_supply_chain_workflow,
)


def _request() -> SupplyChainExploreRequest:
    return SupplyChainExploreRequest(
        company_name="OpenAI",
        product_name="ChatGPT",
        max_depth=3,
        demo_mode=True,
        cached_mode=True,
    )


async def test_expansion_returns_cpu_subgraph() -> None:
    parent = await run_supply_chain_workflow(_request())
    store: dict = {}
    # The parent state is in the default store; copy it into a
    # private store for the child.
    store[parent.run_id] = parent
    child = await expand_supply_chain_workflow(
        parent.run_id,
        "component:cpu",
        product_name="CPU",
        max_depth=2,
        demo_mode=True,
        cached_mode=True,
        store=store,
    )
    assert child.parent_run_id == parent.run_id
    assert child.expanded_from_node_id == "component:cpu"
    assert child.sankey is not None
    node_ids = {n.node_id for n in child.sankey.nodes}
    # The CPU branch must include at least the two CPU vendors.
    for required in ("company:amd", "company:intel"):
        assert required in node_ids, f"missing {required} in expansion"


async def test_expansion_merges_into_parent_sankey() -> None:
    parent = await run_supply_chain_workflow(_request())
    store: dict = {parent.run_id: parent}
    await expand_supply_chain_workflow(
        parent.run_id,
        "component:cpu",
        product_name="CPU",
        max_depth=2,
        demo_mode=True,
        cached_mode=True,
        store=store,
    )
    # The parent's sankey should now include the CPU subgraph nodes.
    node_ids = {n.node_id for n in store[parent.run_id].sankey.nodes}
    assert "company:amd" in node_ids
    assert "company:intel" in node_ids


async def test_expansion_does_not_pollute_parent_state() -> None:
    parent = await run_supply_chain_workflow(_request())
    initial_node_count = len(parent.nodes)
    store: dict = {parent.run_id: parent}
    await expand_supply_chain_workflow(
        parent.run_id,
        "component:cpu",
        product_name="CPU",
        max_depth=2,
        demo_mode=True,
        cached_mode=True,
        store=store,
    )
    # The parent's *node list* (separate from the merged sankey)
    # should be unchanged; the spec only requires the Sankey to be
    # merged, not the raw node list.
    assert len(parent.nodes) == initial_node_count


async def test_expansion_unknown_parent_raises() -> None:
    store: dict = {}
    with pytest.raises(KeyError):
        await expand_supply_chain_workflow(
            "missing-run",
            "component:cpu",
            demo_mode=True,
            cached_mode=True,
            store=store,
        )


async def test_expansion_max_depth_clamped_to_4() -> None:
    parent = await run_supply_chain_workflow(_request())
    store: dict = {parent.run_id: parent}
    with pytest.raises(ValidationError):
        await expand_supply_chain_workflow(
            parent.run_id,
            "component:cpu",
            max_depth=5,  # > 4 not allowed for expansion
            demo_mode=True,
            cached_mode=True,
            store=store,
        )
