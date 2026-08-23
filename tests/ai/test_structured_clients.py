"""Production-protocol tests for typed filing and relation clients."""

import pytest
from pydantic_ai.models.test import TestModel

from src.ai.structured_clients import (
    PydanticAIFilingExtractionClient,
    PydanticAIGenericExtractionClient,
    PydanticAISupplierRelationClient,
    PydanticAISupplyChainClient,
)
from src.config import Settings


def test_filing_client_returns_canonical_chunk_contract() -> None:
    client = PydanticAIFilingExtractionClient(
        model=TestModel(
            custom_output_args={
                "risks": [
                    {
                        "risk_id": "risk-typed",
                        "risk_type": "supply_chain",
                        "risk_factor": "Supplier concentration remains material.",
                        "severity": 4,
                        "evidence_quote": (
                            "The company depends on a concentrated supplier base."
                        ),
                        "source": "sec:test",
                        "filing_section": "section_1a",
                        "confidence": 0.8,
                    }
                ],
                "warnings": [],
                "needs_review": False,
            }
        ),
        settings=Settings(),
    )

    risks, validations, calls = client.extract_risks_chunked(
        "Supplier concentration is a material operational risk.",
        company_name="Issuer",
        year=2025,
        source_id="sec:filing-1",
        chunk_size=1000,
        overlap=0,
        step_name="filing_risk_extractor",
    )

    assert [risk.risk_id for risk in risks] == ["risk-typed"]
    assert validations[0].ok is True
    assert validations[0].pydantic_model == "FilingRiskExtractionOutput"
    assert calls[0].provider == "pydantic_ai"
    assert calls[0].response_structured is not None


def test_supplier_client_returns_validated_relation_batch() -> None:
    client = PydanticAISupplierRelationClient(
        model=TestModel(
            custom_output_args={
                "relations": [
                    {
                        "supplier_name": "Supplier A",
                        "relation_type": "supplied_by",
                        "source_index": 1,
                        "source_url": "https://example.com/supplier-a",
                        "quote": "Supplier A provides the critical component.",
                        "confidence": 0.8,
                    }
                ],
                "warnings": [],
            }
        ),
        settings=Settings(),
    )

    relations, raw = client.extract_supplier_relations(
        prompt="Extract the supported supplier relation.",
        company_name="Issuer",
        product_name="Product",
        max_suppliers=3,
    )

    assert relations[0].supplier_name == "Supplier A"
    assert relations[0].source_url == "https://example.com/supplier-a"
    assert '"relations"' in raw


@pytest.mark.asyncio
async def test_generic_extraction_client_returns_typed_result_in_async_context() -> None:
    client = PydanticAIGenericExtractionClient(
        model=TestModel(
            custom_output_args={
                "entities": [],
                "relations": [],
                "claims": [],
                "evidence": [],
                "warnings": ["no supported facts"],
            }
        ),
        settings=Settings(),
    )

    result = client.extract("Extract only source-backed facts.")

    assert result.warnings == ["no supported facts"]
    assert result.entities == []


def test_production_builders_select_typed_clients(monkeypatch) -> None:
    from src.config import get_settings
    from src.supply_chain.llm import build_supply_chain_llm_client
    from src.workflows.steps.filing_risk_extractor import _build_llm_client

    get_settings.cache_clear()
    monkeypatch.setattr(
        "src.ai.model_factory.build_agent_model",
        lambda _config: TestModel(custom_output_args={"relations": []}),
    )

    supply_client = build_supply_chain_llm_client(None)
    filing_client = _build_llm_client(None)

    assert isinstance(supply_client, PydanticAISupplyChainClient)
    assert isinstance(filing_client, PydanticAIFilingExtractionClient)
    get_settings.cache_clear()
