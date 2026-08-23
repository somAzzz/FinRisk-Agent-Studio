"""Synthetic provider-contract tests without external model requests."""

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.ai.live_acceptance import run_live_acceptance


async def test_live_acceptance_requires_tool_and_typed_output() -> None:
    request_count = 0

    def respond(_messages, info):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="local_probe",
                        args={"value": 7},
                        tool_call_id="probe-1",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={"status": "ok", "observed_value": 7},
                    tool_call_id="output-1",
                )
            ]
        )

    report = await run_live_acceptance(
        provider="test",
        base_url="http://provider.invalid/v1",
        model_name="test-model",
        model=FunctionModel(respond),
    )

    assert report.output_valid is True
    assert report.local_tool_calls == 1
    assert report.requests == 2
