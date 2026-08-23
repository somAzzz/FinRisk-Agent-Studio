"""Typed Pydantic AI Browser Explorer client tests."""

import pytest
from pydantic_ai.models.test import TestModel

from src.ai.browser_client import PydanticAIBrowserClient, build_browser_client
from src.ai.deps import AgentServices
from src.browser.models import BrowserAction
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
async def test_browser_client_returns_validated_action() -> None:
    client = PydanticAIBrowserClient(
        model=TestModel(
            custom_output_args={
                "thought": "Search for current evidence.",
                "action": "search",
                "query": "issuer latest earnings",
                "url": None,
                "selector": None,
            }
        ),
        settings=Settings(),
    )

    action = await client.decide_action("Research issuer", [], [])

    assert isinstance(action, BrowserAction)
    assert action.query == "issuer latest earnings"


def test_browser_client_factory_uses_central_model_factory(monkeypatch) -> None:
    model = TestModel(custom_output_args={"summary": "ok"})
    monkeypatch.setattr("src.ai.browser_client.build_agent_model", lambda _config: model)

    client = build_browser_client(settings=Settings())

    assert client.summary_agent.model is model
