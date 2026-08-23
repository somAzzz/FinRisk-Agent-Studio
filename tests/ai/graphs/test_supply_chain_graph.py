"""Sequential parity tests for the Supply Chain Pydantic Graph."""

from src.ai.graphs.supply_chain import run_supply_chain_graph
from src.supply_chain.models import SupplyChainExploreRequest, SupplyChainExploreState
from src.supply_chain.workflow import run_supply_chain_workflow


def _request() -> SupplyChainExploreRequest:
    return SupplyChainExploreRequest(
        company_name="OpenAI",
        product_name="ChatGPT",
        max_depth=3,
        demo_mode=True,
        cached_mode=True,
    )


async def test_supply_chain_graph_matches_sequential_demo_contract() -> None:
    legacy_initial = SupplyChainExploreState(
        run_id="parity-supply-chain", request=_request()
    )
    graph_initial = SupplyChainExploreState(
        run_id="parity-supply-chain", request=_request()
    )

    legacy = await run_supply_chain_workflow(
        _request(), initial_state=legacy_initial, store={}
    )
    graph = await run_supply_chain_graph(
        _request(), initial_state=graph_initial, store={}
    )

    assert graph.status == legacy.status == "completed"
    assert [event.step_name for event in graph.trace] == [
        event.step_name for event in legacy.trace
    ]
    assert [event.status for event in graph.trace] == [
        event.status for event in legacy.trace
    ]
    assert graph.nodes == legacy.nodes
    assert graph.links == legacy.links
    assert graph.evidence == legacy.evidence
    assert graph.sankey == legacy.sankey
    assert graph.evaluation == legacy.evaluation
    SupplyChainExploreState.model_validate(graph.model_dump(mode="json"))
