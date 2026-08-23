"""Validation and retry gates for structured-output Agents."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from src.ai.agents.structured import (
    FilingRiskExtractionOutput,
    GraphInterpretationOutput,
    ReportGenerationOutput,
    SupplierRelationBatch,
    build_planner_agent,
)
from src.ai.deps import AgentDeps, AgentPermissions
from src.config import Settings
from src.schemas.finrisk import (
    ExtractedRisk,
    GraphInsight,
    NormalizedEvidence,
    RiskReport,
)
from src.supply_chain.llm_extraction import SupplierRelationExtraction


def _risk() -> ExtractedRisk:
    return ExtractedRisk(
        risk_id="risk-1",
        risk_type="supply_chain",
        risk_factor="Critical supplier concentration remains elevated.",
        severity=4,
        evidence_quote="The company depends on a limited supplier group.",
        source="sec_filing:10-k",
        confidence=0.8,
    )


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


def test_graph_insight_requires_evidence_provenance() -> None:
    with pytest.raises(ValidationError, match="supporting evidence"):
        GraphInterpretationOutput(
            insights=[
                GraphInsight(
                    insight_id="graph-1",
                    source_company="Issuer",
                    affected_entity="Supplier",
                    risk_path=["Issuer", "Supplier"],
                    supporting_evidence_ids=[],
                    confidence=0.7,
                )
            ]
        )


def test_report_top_risk_requires_normalized_evidence() -> None:
    report = RiskReport(
        title="Risk report",
        executive_summary="Summary",
        top_risks=[_risk()],
        evidence_table=[
            NormalizedEvidence(
                evidence_id="evidence-1",
                source_type="filing",
                source_name="10-K",
                quote="An evidence quote long enough for the risk.",
                summary="The filing describes supplier concentration.",
                related_risk_ids=[],
                credibility_score=0.9,
                collected_at=datetime.now(UTC),
            )
        ],
        evidence_vs_inference="Evidence is separated from inference.",
        limitations="Only one filing period was reviewed.",
        markdown="# Risk report",
    )

    with pytest.raises(ValidationError, match="risk-1"):
        ReportGenerationOutput(report=report)


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
