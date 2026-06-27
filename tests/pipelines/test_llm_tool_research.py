"""Tests for the LLM tool research CLI helpers."""

from __future__ import annotations

import json

from src.agents.llm_runtime import LLMToolCallRecord, LLMToolRunResult
from src.pipelines.llm_tool_research import result_to_payload, run_research
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


def _result() -> LLMToolRunResult:
    return LLMToolRunResult(
        goal="Find Apple supply chain evidence",
        final_answer="Evidence found. Uncertainty: only one public source was used.",
        tool_calls=[
            LLMToolCallRecord(
                round_id="round-0",
                tool_name="web_search",
                arguments='{"query":"Apple supply chain"}',
            )
        ],
        tool_events=[
            ToolExecutionEvent(
                event_id="event-1",
                round_id="round-0",
                tool_call_id="call-1",
                tool_name="web_search",
                arguments={"query": "Apple supply chain"},
                status="success",
                result_summary=json.dumps(
                    {
                        "data": {
                            "results": [
                                {
                                    "url": "https://example.com/apple",
                                    "title": "Apple supply chain",
                                }
                            ]
                        }
                    }
                ),
                latency_ms=1,
                result_chars=80,
                created_at=utcnow(),
            )
        ],
    )


def test_result_to_payload_includes_required_runner_fields() -> None:
    payload = result_to_payload(
        _result(),
        provider="deepseek",
        tools_scope="finrisk_market",
        trace_path="trace.json",
    )

    assert payload["final_answer"].startswith("Evidence found")
    assert payload["tool_calls"][0]["tool_name"] == "web_search"
    assert payload["source_urls"] == ["https://example.com/apple"]
    assert payload["uncertainty"].startswith("Uncertainty")
    assert payload["trace_path"] == "trace.json"


def test_run_research_writes_json_trace(tmp_path) -> None:
    class Runtime:
        def run(self, query: str) -> LLMToolRunResult:
            result = _result()
            return result.model_copy(update={"goal": query})

    trace_path = tmp_path / "trace.json"
    payload = run_research(
        "Find evidence",
        provider="vllm",
        tools_scope="company_research",
        json_trace_output=trace_path,
        runtime=Runtime(),
    )

    assert payload["trace_path"] == str(trace_path)
    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["query"] == "Find evidence"
    assert saved["source_urls"] == ["https://example.com/apple"]
