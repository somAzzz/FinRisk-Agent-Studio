from __future__ import annotations

import pytest

from src.supply_chain.models import (
    SupplyChainExploreRequest,
    SupplyChainExploreState,
)
from src.supply_chain.steps.graph_builder import SupplyChainGraphBuilderStep


def _state(*, demo_mode: bool = False) -> SupplyChainExploreState:
    return SupplyChainExploreState(
        run_id="sc-test-run",
        request=SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=demo_mode,
            cached_mode=False,
        ),
    )


@pytest.mark.asyncio
async def test_graph_builder_records_fallback_when_neo4j_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    state = await SupplyChainGraphBuilderStep().run(_state())

    assert any(
        "NEO4J_PASSWORD is not set" in event
        and "using in-memory graph" in event
        for event in state.fallback_events
    )


@pytest.mark.asyncio
async def test_graph_builder_uses_injected_graph_client() -> None:
    class FakeGraphClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def run(self, cypher: str, params: dict) -> None:
            self.calls.append((cypher, params))

    client = FakeGraphClient()
    state = await SupplyChainGraphBuilderStep(graph_client=client).run(_state())

    assert state.fallback_events == []
    assert client.calls == []
