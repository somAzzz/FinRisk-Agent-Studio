"""v18 tests for the supply chain FastAPI routes."""

from __future__ import annotations

import asyncio

import pytest

from src.api.store_factory import get_supply_chain_store
from src.api.supply_chain import (
    _force_real_explore_request,
    expand_supply_chain,
    get_supply_chain_sankey,
    get_supply_chain_status,
    list_supply_chain_runs,
    start_supply_chain_explore,
)
from src.supply_chain.models import (
    SankeyPayload,
    SupplyChainEdge,
    SupplyChainExploreRequest,
    SupplyChainExploreState,
    SupplyChainNode,
)


def _reset() -> None:
    """Clear the shared supply-chain backend synchronously.

    The backend's ``clear`` is a coroutine; we drive it on whatever
    event loop is currently running.
    """
    store = get_supply_chain_store()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # pytest-asyncio is in auto mode and there is no
            # synchronous bridge; schedule a task. Because the
            # underlying dict is just ``.clear()`` we can call it
            # directly via the attribute path.
            store._states.clear()  # type: ignore[attr-defined]
        else:
            loop.run_until_complete(store.clear())
    except RuntimeError:
        # No event loop in this thread — fall back to the
        # underlying dict, which is the only path the in-memory
        # backend uses anyway.
        store._states.clear()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _clear_store(monkeypatch):
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_ALLOW_SUPPLY_CHAIN_DEMO", "1")
    _reset()
    yield
    _reset()


async def test_post_explore_returns_202_with_run_id() -> None:
    resp = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            max_depth=3,
            demo_mode=True,
        )
    )
    assert resp.run_id.startswith("sc-run-")
    assert resp.status == "completed"
    assert resp.sankey_url.endswith("/sankey")


def test_api_forces_real_mode_without_test_fixture_flag(monkeypatch) -> None:
    monkeypatch.delenv("FINRISK_ALLOW_SUPPLY_CHAIN_DEMO", raising=False)
    request = SupplyChainExploreRequest(
        company_name="Apple",
        product_name="iPhone",
        demo_mode=True,
        cached_mode=True,
    )

    normalized = _force_real_explore_request(request)

    assert normalized.demo_mode is False
    assert normalized.cached_mode is False


async def test_post_explore_returns_queued_when_background_enabled(monkeypatch) -> None:
    monkeypatch.delenv("FINRISK_SKIP_BACKGROUND", raising=False)
    resp = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            max_depth=3,
            demo_mode=True,
        )
    )
    assert resp.run_id.startswith("sc-run-")
    assert resp.status == "queued"
    status = await get_supply_chain_status(resp.run_id)
    assert status.status in {"queued", "running", "completed", "needs_review"}


async def test_get_status_returns_node_and_link_counts() -> None:
    resp = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        )
    )
    status = await get_supply_chain_status(resp.run_id)
    assert status.node_count > 0
    assert status.link_count > 0
    assert status.evidence_count > 0
    assert isinstance(status.metrics, dict)


async def test_list_supply_chain_runs_returns_recent_runs() -> None:
    first = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        )
    )
    second = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="NVIDIA",
            product_name="GPU",
            demo_mode=True,
        )
    )

    recent = await list_supply_chain_runs(limit=1)

    assert len(recent) == 1
    assert recent[0].run_id == second.run_id
    assert recent[0].run_id != first.run_id


async def test_get_sankey_returns_payload() -> None:
    resp = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        )
    )
    payload = await get_supply_chain_sankey(resp.run_id)
    assert payload.sankey is not None
    assert payload.sankey.nodes
    assert payload.sankey.links


async def test_get_sankey_repairs_legacy_canonical_parent_ids() -> None:
    state = SupplyChainExploreState(
        run_id="sc-run-legacy",
        request=SupplyChainExploreRequest(
            company_name="Tesla",
            product_name="EV motor",
        ),
        sankey=SankeyPayload(
            nodes=[
                SupplyChainNode(
                    node_id="product:ev-motor",
                    node_type="product",
                    label="EV motor",
                    normalized_name="ev motor",
                    depth=0,
                    confidence=0.9,
                ),
                SupplyChainNode(
                    node_id="commodity:rare-earth-elements",
                    node_type="commodity",
                    label="Rare earth elements",
                    normalized_name="rare earth elements",
                    depth=1,
                    parent_node_id="product:ev-motor",
                    confidence=0.8,
                ),
                SupplyChainNode(
                    node_id="commodity:neodymium",
                    node_type="commodity",
                    label="Neodymium",
                    normalized_name="neodymium",
                    depth=2,
                    parent_node_id="commodity:rare-earth-elements",
                    confidence=0.7,
                ),
            ],
            links=[
                SupplyChainEdge(
                    edge_id="e-re",
                    source_node_id="product:ev-motor",
                    target_node_id="commodity:rare-earth-elements",
                    relation_type="hypothesized",
                    value=0.9,
                    confidence=0.8,
                    metadata={"reason": "legacy"},
                )
            ],
            evidence=[],
            warnings=[],
        ),
    )
    await get_supply_chain_store().update(state)

    payload = await get_supply_chain_sankey("sc-run-legacy")

    assert payload.sankey is not None
    neodymium = next(
        node for node in payload.sankey.nodes if node.node_id == "commodity:neodymium"
    )
    assert neodymium.parent_node_id == "commodity:rare-earth-element"


async def test_unknown_run_returns_404() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_supply_chain_status("sc-run-missing")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await get_supply_chain_sankey("sc-run-missing")
    assert exc.value.status_code == 404


async def test_post_expand_returns_child_run_id() -> None:
    parent = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        )
    )
    from src.supply_chain.models import SupplyChainExpandRequest

    resp = await expand_supply_chain(
        SupplyChainExpandRequest(
            parent_run_id=parent.run_id,
            node_id="component:cpu",
            product_name="CPU",
            max_depth=2,
            demo_mode=True,
        )
    )
    assert resp.run_id.startswith("sc-run-")
    assert resp.run_id != parent.run_id
    assert resp.sankey_url.endswith("/sankey")


async def test_post_expand_returns_queued_when_background_enabled(monkeypatch) -> None:
    parent = await start_supply_chain_explore(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
        )
    )
    monkeypatch.delenv("FINRISK_SKIP_BACKGROUND", raising=False)
    from src.supply_chain.models import SupplyChainExpandRequest

    resp = await expand_supply_chain(
        SupplyChainExpandRequest(
            parent_run_id=parent.run_id,
            node_id="component:cpu",
            product_name="CPU",
            max_depth=2,
            demo_mode=True,
        )
    )

    assert resp.run_id.startswith("sc-run-")
    assert resp.status == "queued"
    status = await get_supply_chain_status(resp.run_id)
    assert status.parent_run_id == parent.run_id
    assert status.expanded_from_node_id == "component:cpu"


async def test_post_expand_unknown_parent_returns_404() -> None:
    from fastapi import HTTPException

    from src.supply_chain.models import SupplyChainExpandRequest

    with pytest.raises(HTTPException) as exc:
        await expand_supply_chain(
            SupplyChainExpandRequest(
                parent_run_id="sc-run-missing",
                node_id="component:cpu",
                demo_mode=True,
            )
        )
    assert exc.value.status_code == 404
