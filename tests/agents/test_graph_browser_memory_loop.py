"""V21 graph/browser/memory closed-loop tests."""

from __future__ import annotations

import json

from src.agents.context import AgentContextBuilder
from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.memory import ContextManager, MemoryItem, MemoryStore
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


def _memory(text: str) -> MemoryItem:
    return MemoryItem(
        memory_type="evidence",
        text=text,
        summary=text,
        source_type="web",
        source_url="https://example.com/memory",
        entities=["Apple", "TSMC"],
        tickers=["AAPL"],
        credibility_score=0.8,
        freshness_score=0.8,
        confidence=0.8,
        claim_type="evidence",
        status="active",
    )


def _tool_event() -> ToolExecutionEvent:
    payload = {
        "tool": "graph_path_search",
        "status": "success",
        "data": {
            "paths": [
                {
                    "path_text": (
                        "Apple supply chain risk depends on TSMC Taiwan "
                        "concentration and supplier exposure."
                    ),
                    "evidence_ids": ["graph-ev-1"],
                }
            ]
        },
    }
    return ToolExecutionEvent(
        event_id="graph-event-1",
        round_id="round-0",
        tool_call_id="graph-call-1",
        tool_name="graph_path_search",
        arguments={"source_entity": "AAPL", "target_entity": "TSMC"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


def test_memory_context_enters_runtime_without_becoming_accepted_evidence(
    tmp_path,
) -> None:
    store = MemoryStore(cache_dir=tmp_path)
    memory = store.upsert(
        _memory("Apple supply chain risk depends on TSMC Taiwan concentration.")
    )

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="done",
                tool_events=[_tool_event()],
            )

    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: Runtime(),
        context_builder=AgentContextBuilder(ContextManager(store)),
    )

    state = runtime.run(
        "Assess Apple supply chain risk through TSMC Taiwan concentration",
        workflow_kind="finrisk",
        subject={"ticker": "AAPL", "entities": ["Apple", "TSMC"]},
    )

    assert state.context_pack is not None
    assert memory.memory_id in state.context_pack["selected_memory_ids"]
    assert memory.memory_id not in state.accepted_evidence_ids
    assert state.accepted_evidence_ids
    assert any(t.event_type == "context_pack_selected" for t in state.trace)
