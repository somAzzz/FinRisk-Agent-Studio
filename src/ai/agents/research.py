"""Typed market research Agent and evidence-grounding validators."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from src.ai.deps import AgentDeps


class ResearchEvidence(BaseModel):
    """One source-backed claim returned by the research Agent."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_url: HttpUrl
    evidence_kind: Literal[
        "web", "filing", "transcript", "financial_metric", "graph_path"
    ]
    quote_or_summary: str = Field(min_length=20)
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ResearchAgentOutput(BaseModel):
    """Grounded market-research result with explicit uncertainty."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "needs_review"]
    answer: str = Field(min_length=1)
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    suggested_next_checks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_grounding(self) -> ResearchAgentOutput:
        """Prevent an ungrounded result from being marked complete."""
        if not self.evidence and self.status != "needs_review":
            raise ValueError("research without evidence must be needs_review")
        if not self.evidence and not self.uncertainties:
            raise ValueError("research without evidence must explain uncertainty")
        source_ids = [item.source_id for item in self.evidence]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source_id values must be unique")
        return self


MARKET_RESEARCH_INSTRUCTIONS = """You are the market research agent for a financial-risk workflow.
Use only the tools visible for this run. Every material claim must cite a tool-backed
source_id and HTTP(S) source_url with a non-empty quote or summary. Separate evidence
from inference, state uncertainty, and mark status needs_review when tools return no
usable evidence. Do not provide investment advice."""


def build_market_research_agent(
    model: Model,
    *,
    toolset: AbstractToolset[AgentDeps],
) -> Agent[AgentDeps, ResearchAgentOutput]:
    """Create the first production-oriented typed Pydantic AI Agent."""
    return Agent(
        model,
        output_type=ResearchAgentOutput,
        deps_type=AgentDeps,
        instructions=MARKET_RESEARCH_INSTRUCTIONS,
        toolsets=[toolset],
        name="finrisk_market_research",
    )


def research_output_json_schema() -> dict[str, Any]:
    """Expose the validated output contract for snapshots and API tooling."""
    return ResearchAgentOutput.model_json_schema()


__all__ = [
    "MARKET_RESEARCH_INSTRUCTIONS",
    "ResearchAgentOutput",
    "ResearchEvidence",
    "build_market_research_agent",
    "research_output_json_schema",
]
