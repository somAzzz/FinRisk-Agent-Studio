"""Real-mode LLM supply-chain investigation tests."""

from __future__ import annotations

from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.models import SupplyChainExploreRequest
from src.supply_chain.steps.product_resolver import SupplyChainProductResolverStep
from src.supply_chain.steps.requirement_decomposer import (
    SupplyChainRequirementDecomposerStep,
)
from src.supply_chain.steps.supplier_discovery import SupplyChainSupplierDiscoveryStep
from src.supply_chain.workflow import run_supply_chain_workflow
from src.tools.providers.base import SearchResponse
from src.workflows.state import utcnow


class FakeLLMClient:
    def complete(self, prompt: str, **_kwargs) -> str:
        if "Decompose the product" in prompt:
            return """
            {
              "requirements": [
                {
                  "label": "GPU accelerator",
                  "node_type": "component",
                  "importance": 0.92,
                  "confidence": 0.81,
                  "reason": "Large AI workloads depend on GPU acceleration."
                }
              ]
            }
            """
        return """
        {
          "suppliers": [
            {
              "requirement_node_id": "component:gpu-accelerator",
              "requirement_label": "GPU accelerator",
              "supplier_name": "NVIDIA",
              "ticker": "NVDA",
              "product_or_service": "AI GPUs",
              "confidence": 0.74,
              "uncertainty": "Candidate requires source confirmation."
            }
          ]
        }
        """


class EmptyRouter:
    def search(self, query, intent="general", max_results=5):
        return SearchResponse(
            provider="stub",
            query=query,
            retrieved_at=utcnow(),
            results=[],
        )


def _fake_client_factory(_config: LLMRunConfig) -> FakeLLMClient:
    return FakeLLMClient()


async def test_real_mode_uses_llm_for_requirements_and_supplier_candidates() -> None:
    state = await run_supply_chain_workflow(
        SupplyChainExploreRequest(
            company_name="OpenAI",
            product_name="ChatGPT",
            demo_mode=False,
            cached_mode=False,
            llm_config=LLMRunConfig(provider="deepseek", model="deepseek-chat"),
        ),
        steps=[
            SupplyChainProductResolverStep(),
            SupplyChainRequirementDecomposerStep(
                llm_client_factory=_fake_client_factory,
            ),
            SupplyChainSupplierDiscoveryStep(
                search_router=EmptyRouter(),
                llm_client_factory=_fake_client_factory,
            ),
        ],
    )

    gpu = next(node for node in state.nodes if node.node_id == "component:gpu-accelerator")
    assert gpu.metadata["method"] == "llm_requirement_decomposer"
    assert any(
        edge.source_node_id == "component:gpu-accelerator"
        and edge.target_node_id == "company:nvidia"
        and edge.metadata["method"] == "llm_supplier_discovery"
        for edge in state.links
    )
    assert any(candidate.supplier_name == "NVIDIA" for candidate in state.llm_supplier_candidates)
    assert state.metrics["llm_requirement_count"] == 1
    assert state.metrics["llm_supplier_candidate_count"] == 1
    decomposer_event = next(
        event for event in state.trace if event.step_name == "requirement_decomposer"
    )
    supplier_event = next(
        event for event in state.trace if event.step_name == "supplier_discovery"
    )
    assert decomposer_event.provider_calls[0].provider == "deepseek"
    assert decomposer_event.provider_calls[0].operation == "decompose_requirements"
    assert supplier_event.provider_calls[0].operation == "propose_suppliers"
