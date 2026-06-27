from datetime import UTC, datetime
from typing import Any

from src.agents.llm_runtime import LLMToolAgentRuntime
from src.schemas.finrisk import LLMCall
from src.schemas.tool_trace import ToolBudgetUsage, ToolExecutionEvent
from src.tools.catalog import ProjectTool, ToolCatalog


class FakeToolCallingClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None
        self.last_tool_events: list[ToolExecutionEvent] = []
        self.last_tool_budget_usage: ToolBudgetUsage | None = None

    def chat_with_tools(self, messages, **kwargs):
        self.kwargs = kwargs
        now = datetime.now(UTC)
        self.last_tool_events = [
            ToolExecutionEvent(
                event_id="event-1",
                round_id="round-0",
                tool_call_id="tool-1",
                tool_name="web_search",
                arguments={"query": "AAPL"},
                status="success",
                result_summary="result",
                latency_ms=1,
                result_chars=6,
                created_at=now,
            )
        ]
        self.last_tool_budget_usage = ToolBudgetUsage(
            max_tool_result_chars=12000,
            max_total_tool_result_chars=40000,
            used_tool_result_chars=6,
        )
        call = LLMCall(
            call_id="call-1",
            step_name="local_tool_calling",
            chunk_id="round-0",
            provider="fake",
            model="fake-model",
            messages=messages,
            prompt_text=messages[-1]["content"],
            response_text="",
            response_structured={
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "AAPL"}',
                        },
                    }
                ]
            },
            latency_ms=1,
            started_at=now,
            completed_at=now,
        )
        return "final answer", [call]


def test_llm_tool_agent_runtime_passes_catalog_to_client() -> None:
    client = FakeToolCallingClient()
    catalog = ToolCatalog(
        project_tools=(
            ProjectTool(
                name="web_search",
                description="Search web.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                callable=lambda query: {"query": query},
            ),
        )
    )
    runtime = LLMToolAgentRuntime(
        llm_client=client,
        tool_catalog=catalog,
        max_tool_rounds=2,
        temperature=0,
        max_tool_result_chars=100,
        max_total_tool_result_chars=500,
    )

    result = runtime.run("Research AAPL")

    assert result.final_answer == "final answer"
    assert result.tool_calls[0].tool_name == "web_search"
    assert result.tool_calls[0].arguments == '{"query": "AAPL"}'
    assert result.tool_events[0].tool_name == "web_search"
    assert result.budget_usage is not None
    assert result.budget_usage.used_tool_result_chars == 6
    assert result.mode == "native"
    assert client.kwargs is not None
    assert client.kwargs["tools"] == catalog.tools
    assert list(client.kwargs["tool_map"]) == ["web_search"]
    assert client.kwargs["max_tool_rounds"] == 2
    assert client.kwargs["temperature"] == 0
    assert client.kwargs["max_tool_result_chars"] == 100
    assert client.kwargs["max_total_tool_result_chars"] == 500
