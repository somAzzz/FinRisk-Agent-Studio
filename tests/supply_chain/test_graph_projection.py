from __future__ import annotations

import pytest

from src.supply_chain.models import (
    SupplyChainExploreRequest,
    SupplyChainExploreState,
)
from src.supply_chain.steps.graph_projection import SupplyChainGraphProjectionStep


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
async def test_graph_projection_records_fallback_when_neo4j_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    state = _state()
    state.sankey = None
    state = await SupplyChainGraphProjectionStep().run(state)

    assert any("sankey unavailable" in event for event in state.fallback_events)


@pytest.mark.asyncio
async def test_graph_projection_writes_final_sankey_with_injected_client() -> None:
    from src.supply_chain.models import SankeyPayload, SupplyChainNode

    class FakeGraphClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def run(self, cypher: str, params: dict) -> None:
            self.calls.append((cypher, params))

    state = _state()
    state.sankey = SankeyPayload(
        nodes=[
            SupplyChainNode(
                node_id="product:chatgpt",
                node_type="product",
                label="ChatGPT",
                normalized_name="chatgpt",
                depth=0,
                confidence=0.9,
                metadata={"profile": {"summary": "AI assistant"}},
            )
        ],
        links=[],
        evidence=[],
        warnings=[],
    )
    client = FakeGraphClient()
    state = await SupplyChainGraphProjectionStep(graph_client=client).run(state)

    assert state.fallback_events == []
    cypher = "\n".join(call[0] for call in client.calls)
    assert "MERGE (r:SupplyChainRun" in cypher
    assert "CONTAINS_NODE" in cypher
    run_call = next(call for call in client.calls if "MERGE (r:SupplyChainRun" in call[0])
    assert run_call[1]["props"]["product_name"] == "ChatGPT"
