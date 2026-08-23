"""Typed Agents replacing hand-parsed JSON output boundaries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from src.agents.extraction_agent import ExtractionResult
from src.agents.state import AgentDecision
from src.ai.deps import AgentDeps
from src.schemas.finrisk import ExtractedRisk
from src.supply_chain.llm_extraction import SupplierRelationExtraction
from src.supply_chain.llm_models import (
    NodeProfileBatch,
    RequirementDecomposition,
    SupplierProposalBatch,
)


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


def build_requirement_decomposition_agent(
    model: Model,
) -> Agent[AgentDeps, RequirementDecomposition]:
    return Agent(
        model,
        output_type=RequirementDecomposition,
        deps_type=AgentDeps,
        instructions=(
            "Decompose the product into concrete upstream requirements using "
            "the supplied typed schema. Do not invent unsupported precision."
        ),
        name="supply_chain_requirement_decomposer",
    )


def build_supplier_proposal_agent(
    model: Model,
) -> Agent[AgentDeps, SupplierProposalBatch]:
    return Agent(
        model,
        output_type=SupplierProposalBatch,
        deps_type=AgentDeps,
        instructions=(
            "Propose plausible upstream suppliers as hypotheses using the supplied "
            "typed schema. Never treat an unsupported proposal as confirmed."
        ),
        name="supply_chain_supplier_proposer",
    )


def build_node_profile_agent(
    model: Model,
) -> Agent[AgentDeps, NodeProfileBatch]:
    return Agent(
        model,
        output_type=NodeProfileBatch,
        deps_type=AgentDeps,
        instructions=(
            "Create concise supply-chain node intelligence cards using the supplied "
            "typed schema and only the graph context in the prompt."
        ),
        name="supply_chain_node_profiler",
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


__all__ = [
    "FilingRiskExtractionOutput",
    "SupplierRelationBatch",
    "build_filing_extraction_agent",
    "build_generic_extraction_agent",
    "build_node_profile_agent",
    "build_planner_agent",
    "build_relation_extraction_agent",
    "build_requirement_decomposition_agent",
    "build_supplier_proposal_agent",
]
