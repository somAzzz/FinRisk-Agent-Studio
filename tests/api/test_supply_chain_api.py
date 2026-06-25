"""v18 tests for the supply chain FastAPI routes."""

from __future__ import annotations

import pytest

from src.api.supply_chain import (
    DEFAULT_STATE_STORE,
    expand_supply_chain,
    get_supply_chain_sankey,
    get_supply_chain_status,
    start_supply_chain_explore,
)
from src.supply_chain.models import SupplyChainExploreRequest


def _reset() -> None:
    DEFAULT_STATE_STORE.clear()


@pytest.fixture(autouse=True)
def _clear_store(monkeypatch):
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
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
