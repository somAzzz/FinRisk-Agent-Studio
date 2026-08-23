"""Grounding and typed-output tests for the market research Agent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai import FunctionToolset
from pydantic_ai.models.test import TestModel

from src.ai.agents.research import ResearchAgentOutput, build_market_research_agent
from src.ai.deps import AgentDeps
from src.config import Settings


def test_completed_output_requires_source_backed_evidence() -> None:
    with pytest.raises(ValidationError, match="must be needs_review"):
        ResearchAgentOutput(
            status="completed",
            answer="Risk may be increasing.",
            evidence=[],
            uncertainties=["No current source was returned."],
        )


def test_no_evidence_output_requires_explicit_uncertainty() -> None:
    with pytest.raises(ValidationError, match="explain uncertainty"):
        ResearchAgentOutput(
            status="needs_review",
            answer="No supported conclusion.",
        )


async def test_market_research_agent_returns_validated_typed_output() -> None:
    model = TestModel(
        custom_output_args={
            "status": "completed",
            "answer": "A current source supports the risk.",
            "evidence": [
                {
                    "source_id": "source-1",
                    "source_url": "https://example.com/risk",
                    "evidence_kind": "web",
                    "quote_or_summary": (
                        "A sufficiently detailed source summary supports the risk."
                    ),
                    "claim": "The risk remains active.",
                    "confidence": 0.8,
                }
            ],
            "uncertainties": ["Only one source was available."],
            "suggested_next_checks": ["Check the next filing."],
        }
    )
    agent = build_market_research_agent(
        model,
        toolset=FunctionToolset[AgentDeps](),
    )

    result = await agent.run(
        "Research a market risk.",
        deps=AgentDeps(run_id="research-1", settings=Settings()),
    )

    assert result.output.status == "completed"
    assert result.output.evidence[0].source_id == "source-1"
    assert str(result.output.evidence[0].source_url).startswith("https://")
