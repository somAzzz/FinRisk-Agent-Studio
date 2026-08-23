"""Tests for the LLM tool research CLI helpers."""

from __future__ import annotations

import inspect
import json

from pydantic_ai.models.test import TestModel

from src.ai import model_factory
from src.ai.model_factory import SGLangModelConfig, VLLMModelConfig
from src.ai.runtime_adapter import PydanticAIRuntimeAdapter
from src.ai.runtime_types import LLMToolCallRecord, LLMToolRunResult
from src.pipelines import llm_tool_research
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


def test_build_runtime_returns_pydantic_adapter_without_network(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_agent_model(config: SGLangModelConfig) -> TestModel:
        captured["config"] = config
        return TestModel(custom_output_text="adapter answer")

    monkeypatch.setattr(model_factory, "build_agent_model", fake_build_agent_model)

    runtime = llm_tool_research.build_runtime(
        provider="sglang",
        tools_scope="company_research",
        max_tool_rounds=2,
    )

    assert isinstance(runtime, PydanticAIRuntimeAdapter)
    assert isinstance(runtime.deps.budget.max_tool_rounds_per_subgoal, int)
    assert runtime.deps.permissions.tool_scopes == frozenset({"company_research"})
    assert runtime.deps.permissions.allow_write is False
    assert runtime.deps.permissions.allow_interactive is False

    result = runtime.run("Find evidence")
    assert result.goal == "Find evidence"
    assert result.final_answer == "adapter answer"
    assert result.mode == "native"

    config = captured["config"]
    assert config.provider == "sglang"
    assert config.model == "Qwen/Qwen3.5-35B-A3B"
    assert config.base_url == "http://localhost:30000/v1"


def test_build_runtime_forwards_overrides_without_legacy_clients(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_agent_model(config: VLLMModelConfig) -> TestModel:
        captured["config"] = config
        return TestModel(custom_output_text="ok")

    monkeypatch.setattr(model_factory, "build_agent_model", fake_build_agent_model)
    monkeypatch.setattr(
        model_factory,
        "resolve_agent_model_config",
        lambda run_config, settings=None: VLLMModelConfig(
            base_url=run_config.base_url or "http://localhost:8000/v1",
            model=run_config.model or "Qwen/Qwen3.5-35B-A3B",
            api_key="dummy",
        ),
    )

    llm_tool_research.build_runtime(
        provider="vllm",
        tools_scope="finrisk_market",
        max_tool_rounds=1,
        model="custom-model",
        base_url="http://127.0.0.1:8000/v1",
    )

    config = captured["config"]
    assert config.provider == "vllm"
    assert config.model == "custom-model"
    assert config.base_url == "http://127.0.0.1:8000/v1"

    module_source = inspect.getsource(llm_tool_research)
    for legacy_name in (
        "LLMToolAgentRuntime",
        "EdgarLLMClient",
        "DeepSeekClient",
        "tool_loop_mode",
    ):
        assert legacy_name not in module_source
