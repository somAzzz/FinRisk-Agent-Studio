"""Typed Agents replacing hand-parsed JSON output boundaries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from src.agents.extraction_agent import ExtractionResult
from src.agents.state import AgentDecision
from src.ai.deps import AgentDeps
from src.schemas.finrisk import ExtractedRisk, GraphInsight, RiskReport
from src.supply_chain.llm_extraction import SupplierRelationExtraction


class SupplierRelationBatch(BaseModel):
    """Validated supply-chain relations with accepted-evidence rules."""

    model_config = ConfigDict(extra="forbid")

    relations: list[SupplierRelationExtraction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_confirmed_relations(self) -> SupplierRelationBatch:
        for relation in self.relations:
            confirmed = (
                relation.relation_type != "hypothesized"
                and relation.confidence >= 0.55
            )
            if confirmed and (
                not relation.source_url
                or not relation.source_url.startswith(("http://", "https://"))
                or not relation.quote.strip()
            ):
                raise ValueError(
                    "confirmed supplier relations require URL-backed evidence"
                )
        return self


class FilingRiskExtractionOutput(BaseModel):
    """Typed filing risks plus explicit extraction warnings."""

    model_config = ConfigDict(extra="forbid")

    risks: list[ExtractedRisk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_review: bool = False

    @model_validator(mode="after")
    def validate_empty_result(self) -> FilingRiskExtractionOutput:
        if not self.risks and not self.needs_review:
            raise ValueError("empty filing extraction must be marked needs_review")
        return self


class GraphInterpretationOutput(BaseModel):
    """Graph insights whose provenance IDs remain resolvable."""

    model_config = ConfigDict(extra="forbid")

    insights: list[GraphInsight] = Field(default_factory=list)
    unresolved_evidence_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False

    @model_validator(mode="after")
    def validate_provenance(self) -> GraphInterpretationOutput:
        if any(not item.supporting_evidence_ids for item in self.insights):
            raise ValueError("every graph insight requires supporting evidence IDs")
        if self.unresolved_evidence_ids and not self.needs_review:
            raise ValueError("unresolved graph provenance requires review")
        return self


class ReportGenerationOutput(BaseModel):
    """Final report wrapper enforcing evidence for every top risk."""

    model_config = ConfigDict(extra="forbid")

    report: RiskReport
    needs_review: bool = False

    @model_validator(mode="after")
    def validate_top_risk_evidence(self) -> ReportGenerationOutput:
        supported_risk_ids = {
            risk_id
            for evidence in self.report.evidence_table
            for risk_id in evidence.related_risk_ids
        }
        missing = [
            risk.risk_id
            for risk in self.report.top_risks
            if risk.risk_id not in supported_risk_ids
        ]
        if missing:
            raise ValueError(
                "report top risks missing normalized evidence: "
                + ", ".join(missing)
            )
        return self


def build_relation_extraction_agent(
    model: Model,
) -> Agent[AgentDeps, SupplierRelationBatch]:
    return Agent(
        model,
        output_type=SupplierRelationBatch,
        deps_type=AgentDeps,
        instructions=(
            "Extract only source-backed supplier relations. Confirmed relations "
            "must include an HTTP(S) source_url and a verbatim quote."
        ),
        name="supply_chain_relation_extractor",
    )


def build_filing_extraction_agent(
    model: Model,
) -> Agent[AgentDeps, FilingRiskExtractionOutput]:
    return Agent(
        model,
        output_type=FilingRiskExtractionOutput,
        deps_type=AgentDeps,
        instructions=(
            "Extract filing risks supported by the provided filing text. "
            "Mark needs_review when no supported risk can be extracted."
        ),
        name="filing_risk_extractor",
    )


def build_generic_extraction_agent(
    model: Model,
) -> Agent[AgentDeps, ExtractionResult]:
    return Agent(
        model,
        output_type=ExtractionResult,
        deps_type=AgentDeps,
        instructions="Extract typed entities, relations, claims, and evidence.",
        name="generic_structured_extractor",
    )


def build_planner_agent(
    model: Model,
) -> Agent[AgentDeps, AgentDecision]:
    agent: Agent[AgentDeps, AgentDecision] = Agent(
        model,
        output_type=AgentDecision,
        deps_type=AgentDeps,
        instructions=(
            "Choose only tool scopes and tools allowed by the injected run "
            "permissions. Return one typed AgentDecision."
        ),
        name="typed_agent_planner",
    )

    @agent.output_validator
    def validate_planner_scope(
        ctx: RunContext[AgentDeps], decision: AgentDecision
    ) -> AgentDecision:
        pending_subgoal_id = ctx.deps.subject.metadata.get(
            "pending_subgoal_id"
        )
        if pending_subgoal_id and (
            decision.decision_type != "call_tools"
            or decision.subgoal_id != pending_subgoal_id
        ):
            raise ModelRetry(
                "A pending subgoal exists; return call_tools for subgoal_id "
                f"{pending_subgoal_id}."
            )
        scopes = {
            scope
            for scope in [
                decision.selected_tool_scope,
                *(item.tool_scope for item in decision.next_subgoals),
            ]
            if scope is not None
        }
        invalid = scopes - ctx.deps.permissions.tool_scopes
        if invalid:
            raise ModelRetry(
                "Unknown or unauthorized tool scopes: "
                + ", ".join(sorted(invalid))
            )
        visible_tools = set(ctx.deps.visible_tool_catalog().names)
        unknown_tools = set(decision.selected_tools) - visible_tools
        if unknown_tools:
            raise ModelRetry(
                "Unknown or unauthorized tools: "
                + ", ".join(sorted(unknown_tools))
            )
        return decision

    return agent


def build_graph_interpretation_agent(
    model: Model,
) -> Agent[AgentDeps, GraphInterpretationOutput]:
    return Agent(
        model,
        output_type=GraphInterpretationOutput,
        deps_type=AgentDeps,
        instructions=(
            "Interpret graph paths without inventing nodes or evidence IDs. "
            "Flag unresolved provenance as needs_review."
        ),
        name="graph_insight_interpreter",
    )


def build_report_generation_agent(
    model: Model,
) -> Agent[AgentDeps, ReportGenerationOutput]:
    return Agent(
        model,
        output_type=ReportGenerationOutput,
        deps_type=AgentDeps,
        instructions=(
            "Generate a research-only risk report. Every top risk must map to "
            "normalized evidence and the report must retain limitations."
        ),
        name="typed_risk_report_generator",
    )


__all__ = [
    "FilingRiskExtractionOutput",
    "GraphInterpretationOutput",
    "ReportGenerationOutput",
    "SupplierRelationBatch",
    "build_filing_extraction_agent",
    "build_generic_extraction_agent",
    "build_graph_interpretation_agent",
    "build_planner_agent",
    "build_relation_extraction_agent",
    "build_report_generation_agent",
]
