"""Production-callable tests for the typed Pydantic AI planner."""

from pydantic_ai.models.test import TestModel

from src.agents.state import AgentRunState, AgentSubgoal
from src.ai.deps import AgentServices
from src.ai.message_store import InMemoryAgentMessageStore
from src.ai.planner_adapter import PydanticAIPlanner
from src.ai.recorder import AgentRunRecorder
from src.config import Settings
from src.tools.contracts import ProjectTool, ToolCatalog


def test_typed_planner_validates_pending_subgoal_and_records_usage() -> None:
    subgoal = AgentSubgoal(
        subgoal_id="sg-pending",
        objective="Collect filing evidence.",
        tool_scope="company_research",
    )
    model = TestModel(
        custom_output_args={
            "decision_type": "call_tools",
            "subgoal_id": "sg-pending",
            "rationale": "Inspect the filing source.",
            "selected_tool_scope": "company_research",
            "selected_tools": ["web_search"],
            "confidence": 0.8,
        }
    )
    catalog = ToolCatalog(
        project_tools=(
            ProjectTool(
                name="web_search",
                description="Search.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                callable=lambda query: {"query": query},
                scopes=frozenset({"company_research"}),
            ),
        )
    )
    store = InMemoryAgentMessageStore()
    planner = PydanticAIPlanner(
        model=model,
        settings=Settings(),
        tool_catalog=catalog,
        services=AgentServices(
            tool_catalog=catalog,
            message_recorder=AgentRunRecorder(store),
        ),
    )
    state = AgentRunState(
        run_id="planner-run",
        user_goal="Research Apple",
        subgoals=[subgoal],
    )

    decision = planner(state)

    assert decision["decision_type"] == "call_tools"
    assert decision["subgoal_id"] == "sg-pending"
    assert state.trace[-1].event_type == "pydantic_ai_planner"
