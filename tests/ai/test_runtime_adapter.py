"""Compatibility tests for the Pydantic AI SubgoalRuntime adapter."""

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from src.ai.deps import AgentDeps, AgentServices
from src.ai.message_store import InMemoryAgentMessageStore
from src.ai.recorder import AgentRunRecorder
from src.ai.runtime_adapter import PydanticAIRuntimeAdapter
from src.config import Settings
from src.tools.contracts import ProjectTool, ToolCatalog


def test_adapter_satisfies_legacy_subgoal_result_contract() -> None:
    tool = ProjectTool(
        name="web_search",
        description="Search web.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        callable=lambda query, **_: {
            "query": query,
            "url": "https://example.com/evidence",
        },
        scopes=frozenset({"company_research"}),
        evidence_kind="web",
    )
    catalog = ToolCatalog(project_tools=(tool,))
    deps = AgentDeps(
        run_id="adapter-1",
        settings=Settings(),
        services=AgentServices(tool_catalog=catalog),
    )
    runtime = PydanticAIRuntimeAdapter(
        model=TestModel(call_tools=["web_search"]),
        deps=deps,
        system_prompt="Collect one source.",
    )

    result = runtime.run("Research AAPL")

    assert result.goal == "Research AAPL"
    assert result.final_answer
    assert result.mode == "native"
    assert result.tool_calls[0].tool_name == "web_search"
    assert result.tool_events[0].tool_name == "web_search"
    assert result.tool_events[0].status == "success"
    assert result.budget_usage is not None
    assert result.budget_usage.used_tool_result_chars > 0


def test_adapter_continues_from_server_side_conversation_history() -> None:
    observed_message_counts: list[int] = []

    def respond(messages, _info):
        observed_message_counts.append(len(messages))
        return ModelResponse(parts=[TextPart(content="completed")])

    catalog = ToolCatalog(project_tools=())
    recorder = AgentRunRecorder(InMemoryAgentMessageStore())

    def run(run_id: str, goal: str) -> None:
        deps = AgentDeps(
            run_id=run_id,
            conversation_id="conversation-1",
            load_message_history=True,
            settings=Settings(),
            services=AgentServices(
                tool_catalog=catalog,
                message_recorder=recorder,
            ),
        )
        PydanticAIRuntimeAdapter(
            model=FunctionModel(respond),
            deps=deps,
            system_prompt="Continue the conversation.",
        ).run(goal)

    run("run-1", "first turn")
    run("run-2", "second turn")

    assert observed_message_counts == [1, 3]
