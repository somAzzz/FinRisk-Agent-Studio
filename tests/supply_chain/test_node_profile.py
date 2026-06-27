"""Tests for supply-chain node intelligence profiles."""

from __future__ import annotations

from src.supply_chain.models import (
    SupplyChainExploreRequest,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps.node_profile import SupplyChainNodeProfileStep
from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
from src.supply_chain.workflow import run_supply_chain_workflow


class _FakeProfileClient:
    def complete(
        self,
        _prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        _ = (system, max_tokens, temperature)
        return """
        {
          "profiles": [
            {
              "node_id": "commodity:rare-earth-minerals",
              "summary": "Rare earth minerals support magnets and power electronics.",
              "key_items": ["Neodymium", "Dysprosium"],
              "applications": ["Permanent magnets"],
              "risk_factors": ["Export controls"],
              "comparable_entities": ["Lithium"],
              "confidence": 0.82
            }
          ]
        }
        """


async def test_demo_workflow_adds_taxonomy_node_profiles() -> None:
    state = await run_supply_chain_workflow(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=True,
            cached_mode=True,
        )
    )

    assert state.sankey is not None
    gpu = next(
        node
        for node in state.sankey.nodes
        if node.node_id == "component:gpu-accelerator"
    )
    profile = gpu.metadata.get("profile")
    assert isinstance(profile, dict)
    assert "GPU" in profile["summary"] or "dependency" in profile["summary"]
    assert profile["generated_by"] == "taxonomy"


async def test_real_mode_node_profile_prefers_llm_output() -> None:
    state = SupplyChainExploreState(
        run_id="sc-run-profile",
        request=SupplyChainExploreRequest(
            company_name="Acme",
            product_name="AI server",
            demo_mode=False,
            cached_mode=False,
        ),
    )
    state = await SupplyChainProductResolverStep().run(state)
    state.nodes.append(
        SupplyChainNode(
            node_id="commodity:rare-earth-minerals",
            node_type="commodity",
            label="Rare earth minerals",
            normalized_name="rare earth minerals",
            depth=1,
            parent_node_id="product:ai-server",
            confidence=0.7,
            evidence_ids=[],
            metadata={},
        )
    )
    step = SupplyChainNodeProfileStep(
        llm_client_factory=lambda _config: _FakeProfileClient()
    )

    state = await step.run(state)

    node = next(n for n in state.nodes if n.node_id == "commodity:rare-earth-minerals")
    profile = node.metadata.get("profile")
    assert isinstance(profile, dict)
    assert profile["summary"] == "Rare earth minerals support magnets and power electronics."
    assert profile["generated_by"] == "llm"
    assert profile["key_items"] == ["Neodymium", "Dysprosium"]
