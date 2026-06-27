"""LLM-driven MarketExplorerStep migration tests."""

from __future__ import annotations

import json

from src.agents.llm_runtime import LLMToolRunResult
from src.schemas.finrisk import (
    CompanyProfile,
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    utcnow,
)
from src.schemas.tool_trace import ToolBudgetUsage, ToolExecutionEvent
from src.tools.providers.base import SearchResponse, SearchResult
from src.workflows.steps.market_explorer_step import MarketExplorerStep


def _state() -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="run-llm-market",
        request=FinRiskRequest(
            ticker="AAPL",
            analysis_goal="Assess supply chain pressure",
            demo_mode=False,
        ),
        company=CompanyProfile(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            filing_type="10-K",
            analysis_year=2025,
            source="fixture",
            resolved_at=utcnow(),
        ),
        filing_risks=[
            ExtractedRisk(
                risk_id="risk-supply",
                risk_type="supply_chain",
                risk_factor="Apple depends on external manufacturers in Asia",
                severity=4,
                evidence_quote="outsourcing partners are primarily located in Asia",
                source="sec_filing:test",
                filing_section="section_1a",
                confidence=0.8,
            )
        ],
    )


def _tool_event(payload: dict, *, name: str = "web_search") -> ToolExecutionEvent:
    return ToolExecutionEvent(
        event_id=f"event-{name}",
        round_id="round-0",
        tool_call_id=f"call-{name}",
        tool_name=name,
        arguments={"query": "Apple supplier pressure"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=len(json.dumps(payload)),
        created_at=utcnow(),
    )


def _deterministic_router_result() -> SearchResponse:
    return SearchResponse(
        provider="fake",
        query="Apple supply chain",
        retrieved_at=utcnow(),
        results=[
            SearchResult(
                title="Apple deterministic evidence",
                url="https://example.com/deterministic",
                snippet="Deterministic supplier pressure evidence is available.",
                rank=1,
            )
        ],
    )


async def test_market_explorer_llm_primary_uses_tool_events_as_evidence() -> None:
    state = _state()

    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "provider": "fake",
            "query": "Apple supplier pressure",
            "retrieved_at": utcnow().isoformat(),
            "results": [
                {
                    "title": "Apple supplier pressure",
                    "url": "https://www.reuters.com/technology/apple-suppliers",
                    "snippet": (
                        "Apple suppliers face pressure from regional production "
                        "disruption and component availability."
                    ),
                    "rank": 1,
                }
            ],
        },
        "evidence_kind": "web",
        "warnings": [],
        "truncated": False,
    }

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="Evidence found.",
                tool_events=[_tool_event(payload)],
                budget_usage=ToolBudgetUsage(
                    max_tool_result_chars=12000,
                    max_total_tool_result_chars=40000,
                    used_tool_result_chars=300,
                ),
            )

    class Router:
        def search(self, *_args, **_kwargs):
            raise AssertionError("deterministic router should not run")

    step = MarketExplorerStep(
        search_router=Router,
        llm_runtime_factory=Runtime,
        llm_mode="primary",
    )

    new_state = await step.run(state)

    assert len(new_state.market_evidence) == 1
    assert new_state.market_evidence[0].risk_id == "risk-supply"
    assert new_state.market_evidence[0].source_type == "financial"
    assert "component availability" in new_state.market_evidence[0].evidence_summary
    assert len(new_state.tool_traces) == 1
    assert not new_state.fallback_events


async def test_market_explorer_llm_primary_falls_back_on_runtime_error() -> None:
    state = _state()

    class Runtime:
        def run(self, _goal: str) -> LLMToolRunResult:
            raise RuntimeError("model offline")

    class Router:
        def search(self, *_args, **_kwargs):
            return _deterministic_router_result()

    step = MarketExplorerStep(
        search_router=Router,
        llm_runtime_factory=Runtime,
        llm_mode="primary",
    )

    new_state = await step.run(state)

    assert len(new_state.market_evidence) == 1
    assert new_state.market_evidence[0].source_url == "https://example.com/deterministic"
    assert any(event.from_mode == "llm_primary" for event in new_state.fallback_events)


async def test_market_explorer_llm_primary_falls_back_on_low_quality_evidence() -> None:
    state = _state()
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "provider": "fake",
            "query": "Apple rumor",
            "retrieved_at": utcnow().isoformat(),
            "results": [
                {
                    "title": "Thin rumor",
                    "url": "not-a-url",
                    "snippet": "too short",
                    "rank": 1,
                }
            ],
        },
        "evidence_kind": "web",
        "warnings": [],
        "truncated": False,
    }

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="No strong evidence.",
                tool_events=[_tool_event(payload)],
            )

    class Router:
        def search(self, *_args, **_kwargs):
            return _deterministic_router_result()

    step = MarketExplorerStep(
        search_router=Router,
        llm_runtime_factory=Runtime,
        llm_mode="primary",
    )

    new_state = await step.run(state)

    assert len(new_state.market_evidence) == 1
    assert new_state.market_evidence[0].source_url == "https://example.com/deterministic"
    assert any(
        event.from_mode == "llm_primary"
        and "no source-backed market evidence" in event.reason
        for event in new_state.fallback_events
    )
