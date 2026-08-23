"""Typed Pydantic AI Browser Explorer client tests."""

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from src.ai.browser_client import PydanticAIBrowserClient, build_browser_client
from src.ai.deps import AgentServices
from src.browser.models import BrowserAction, BrowserExplorationOutcome
from src.config import Settings


@pytest.mark.asyncio
async def test_browser_client_returns_typed_page_summary() -> None:
    client = PydanticAIBrowserClient(
        model=TestModel(custom_output_args={"summary": "Markets moved higher."}),
        settings=Settings(),
    )

    summary = await client.summarize("The market moved higher after earnings.")

    assert summary == "Markets moved higher."


@pytest.mark.asyncio
async def test_browser_client_records_agent_messages() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls = []

        async def record_result(self, **kwargs) -> None:
            self.calls.append(kwargs)

    recorder = Recorder()
    client = PydanticAIBrowserClient(
        model=TestModel(custom_output_args={"summary": "Recorded summary."}),
        settings=Settings(),
        services=AgentServices(message_recorder=recorder),  # type: ignore[arg-type]
        conversation_id="browser:test",
    )

    await client.summarize("A sufficiently detailed financial page.")

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["conversation_id"] == "browser:test"
    assert recorder.calls[0]["agent_name"] == "browser_page_summarizer"


@pytest.mark.asyncio
async def test_browser_client_runs_validated_action_as_agent_tool() -> None:
    request_count = 0

    def respond(_messages, info):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="browser_action",
                        args={
                            "action": {
                                "thought": "Search for current evidence.",
                                "action": "search",
                                "query": "issuer latest earnings",
                                "url": None,
                                "selector": None,
                            }
                        },
                        tool_call_id="browser-1",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={
                        "summary": "Search results were inspected.",
                        "stop_reason": "enough_evidence",
                    },
                    tool_call_id="browser-output-1",
                )
            ]
        )

    class Session:
        def __init__(self) -> None:
            self.actions = []

        async def execute(self, action: BrowserAction):
            self.actions.append(action)
            return {"success": True, "stop_recommended": True}

    session = Session()
    client = PydanticAIBrowserClient(
        model=FunctionModel(respond),
        settings=Settings(),
    )

    outcome = await client.explore(
        goal="Research issuer",
        visited_urls=[],
        recent_findings=[],
        session=session,
        max_steps=2,
    )

    assert isinstance(outcome, BrowserExplorationOutcome)
    assert outcome.stop_reason == "enough_evidence"
    assert session.actions[0].query == "issuer latest earnings"
    assert request_count == 2


def test_browser_client_factory_uses_central_model_factory(monkeypatch) -> None:
    model = TestModel(custom_output_args={"summary": "ok"})
    monkeypatch.setattr("src.ai.browser_client.build_agent_model", lambda _config: model)

    client = build_browser_client(settings=Settings())

    assert client.summary_agent.model is model
