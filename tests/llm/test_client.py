import json
from unittest.mock import MagicMock, patch

from src.llm.client import EdgarLLMClient


def test_complete_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "complete")
    assert callable(client.complete)


def test_compute_embedding_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "compute_embedding")
    assert callable(client.compute_embedding)


def test_edgar_client_complete_with_tools_uses_openai_compatible_tools():
    tool_call = MagicMock()
    tool_call.id = "call-local"
    tool_call.type = "function"
    tool_call.function.name = "lookup_metric"
    tool_call.function.arguments = json.dumps({"ticker": "AAPL"})

    first = MagicMock()
    first.choices = [
        MagicMock(message=MagicMock(content="", tool_calls=[tool_call]))
    ]
    second = MagicMock()
    second.choices = [
        MagicMock(message=MagicMock(content="AAPL: 0.46", tool_calls=None))
    ]
    tools = [{"type": "function", "function": {"name": "lookup_metric"}}]

    with patch("src.llm.client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.side_effect = [first, second]
        client = EdgarLLMClient(model="local-model", provider="sglang")
        text = client.complete_with_tools(
            "Find margin.",
            tools=tools,
            tool_map={"lookup_metric": lambda ticker: {"ticker": ticker, "value": 0.46}},
            tool_choice={"type": "function", "function": {"name": "lookup_metric"}},
        )

    assert text == "AAPL: 0.46"
    assert sdk.chat.completions.create.call_count == 2
    first_kwargs = sdk.chat.completions.create.call_args_list[0].kwargs
    second_kwargs = sdk.chat.completions.create.call_args_list[1].kwargs
    assert first_kwargs["model"] == "local-model"
    assert first_kwargs["tools"] == tools
    assert first_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "lookup_metric"},
    }
    assert second_kwargs["tool_choice"] == "auto"
    assert second_kwargs["messages"][-1]["tool_call_id"] == "call-local"
