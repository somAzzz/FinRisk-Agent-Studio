import json
from unittest.mock import MagicMock, patch

from src.llm.client import EdgarLLMClient
from src.schemas.finrisk import LLMCall
from src.workflows.state import utcnow


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


def test_extract_risks_chunked_builds_stable_chunk_ids_without_chunk_field():
    client = EdgarLLMClient(model="local-model", provider="sglang")
    calls: list[LLMCall] = []

    def fake_chat(
        messages,
        *,
        step_name,
        chunk_id,
        max_tokens=None,
        temperature=None,
        emit_call=True,
    ):
        call = LLMCall(
            call_id="llm-test",
            step_name=step_name,
            chunk_id=chunk_id,
            provider="sglang",
            model="local-model",
            messages=messages,
            prompt_text=messages[-1]["content"],
            response_text=json.dumps(
                {
                    "risks": [
                        {
                            "risk_factor": "Supplier concentration risk",
                            "risk_type": "supply_chain",
                            "severity": 4,
                            "quote": "supplier concentration could disrupt production",
                        }
                    ]
                }
            ),
            latency_ms=0,
            started_at=utcnow(),
            completed_at=utcnow(),
        )
        calls.append(call)
        return call.response_text, call

    client._chat = fake_chat  # type: ignore[method-assign]
    risks, validations, returned_calls = client.extract_risks_chunked(
        "supplier concentration could disrupt production. " * 20,
        company_name="Apple Inc.",
        year=2026,
        source_id="sec:0000320193-26-000013",
        chunk_size=120,
        overlap=20,
    )

    assert risks
    assert validations
    assert returned_calls
    assert calls[0].chunk_id == "sec:0000320193-26-000013:section_1a:0-120"
    assert validations[0].chunk_id == calls[0].chunk_id
