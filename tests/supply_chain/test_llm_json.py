"""Typed Pydantic AI contracts for supply-chain analysis."""

from __future__ import annotations

from pydantic_ai.models.test import TestModel

from src.ai.structured_clients import PydanticAISupplyChainClient
from src.config import Settings
from src.supply_chain.llm import call_with_trace


def test_supply_chain_client_returns_typed_requirement_output() -> None:
    client = PydanticAISupplyChainClient(
        model=TestModel(
            custom_output_args={
                "requirements": [
                    {
                        "label": "Advanced packaging",
                        "node_type": "infrastructure",
                        "importance": 0.8,
                        "confidence": 0.7,
                        "reason": "Needed for accelerator integration.",
                    }
                ]
            }
        ),
        settings=Settings(),
    )

    output, call = call_with_trace(
        provider="sglang",
        operation="decompose_requirements",
        call=lambda: client.decompose_requirements("Decompose the product."),
    )

    assert output is not None
    assert output.requirements[0].label == "Advanced packaging"
    assert output.requirements[0].node_type == "infrastructure"
    assert call.status == "success"


def test_supply_chain_client_returns_typed_supplier_output() -> None:
    client = PydanticAISupplyChainClient(
        model=TestModel(
            custom_output_args={
                "suppliers": [
                    {
                        "requirement_node_id": "component:hbm-memory",
                        "requirement_label": "HBM memory",
                        "supplier_name": "SK hynix",
                        "ticker": None,
                        "product_or_service": "HBM3",
                        "confidence": 0.86,
                        "uncertainty": "Requires source confirmation.",
                    }
                ]
            }
        ),
        settings=Settings(),
    )

    output = client.propose_suppliers("Propose suppliers.")

    assert output.suppliers[0].supplier_name == "SK hynix"
    assert output.suppliers[0].requirement_label == "HBM memory"


def test_supply_chain_client_returns_typed_profile_output() -> None:
    client = PydanticAISupplyChainClient(
        model=TestModel(
            custom_output_args={
                "profiles": [
                    {
                        "node_id": "commodity:rare-earth-minerals",
                        "summary": "Rare earth inputs support power electronics.",
                        "key_items": ["Neodymium"],
                        "applications": ["Permanent magnets"],
                        "risk_factors": ["Export controls"],
                        "comparable_entities": ["Lithium"],
                        "confidence": 0.82,
                    }
                ]
            }
        ),
        settings=Settings(),
    )

    output = client.profile_nodes("Profile the nodes.")

    assert output.profiles[0].node_id == "commodity:rare-earth-minerals"
    assert output.profiles[0].key_items == ["Neodymium"]


def test_typed_trace_records_validation_failure() -> None:
    client = PydanticAISupplyChainClient(
        model=TestModel(custom_output_args={"requirements": [{"label": ""}]}),
        settings=Settings(),
    )

    output, call = call_with_trace(
        provider="sglang",
        operation="decompose_requirements",
        call=lambda: client.decompose_requirements("Decompose the product."),
        retries=0,
    )

    assert output is None
    assert call.status == "failed"
    assert call.error
