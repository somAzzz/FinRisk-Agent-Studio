"""Validation and retry gates for structured-output Agents."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from src.ai.agents.structured import (
    FilingRiskExtractionOutput,
    SupplierRelationBatch,
    build_planner_agent,
)
from src.ai.deps import AgentDeps, AgentPermissions
from src.config import Settings
from src.supply_chain.llm_extraction import SupplierRelationExtraction


def test_confirmed_supplier_relation_requires_url_evidence() -> None:
    with pytest.raises(ValidationError, match="URL-backed evidence"):
        SupplierRelationBatch(
            relations=[
                SupplierRelationExtraction(
                    supplier_name="Supplier A",
                    relation_type="supplied_by",
                    quote="Supplier A provides a critical component.",
                    confidence=0.8,
                )
            ]
        )


def test_empty_filing_extraction_cannot_succeed_silently() -> None:
    with pytest.raises(ValidationError, match="needs_review"):
        FilingRiskExtractionOutput(risks=[])


async def test_planner_retries_unauthorized_scope_then_fails_locally() -> None:
    agent = build_planner_agent(
        TestModel(
            custom_output_args={
                "decision_type": "call_tools",
                "rationale": "Use an unknown scope.",
                "selected_tool_scope": "admin_write",
                "confidence": 0.8,
            }
        )
    )
    deps = AgentDeps(
        run_id="planner-1",
        settings=Settings(),
        permissions=AgentPermissions(
            tool_scopes=frozenset({"company_research"})
        ),
    )

    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        await agent.run("Choose the next research action.", deps=deps)
