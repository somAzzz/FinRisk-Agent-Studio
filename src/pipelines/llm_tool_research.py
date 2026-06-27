"""CLI runner for real-case LLM tool-loop research.

Example:

    uv run python -m src.pipelines.llm_tool_research \
      --provider deepseek \
      --tools finrisk_market \
      --query "Find evidence about Apple's supply chain risk."
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

from src.agents.llm_runtime import LLMToolAgentRuntime, LLMToolRunResult
from src.tools.catalog import build_project_tool_catalog

ProviderChoice = Literal["deepseek", "vllm", "sglang"]
ToolScope = Literal["company_research", "finrisk_market", "supply_chain"]


def build_runtime(
    *,
    provider: ProviderChoice,
    tools_scope: ToolScope,
    max_tool_rounds: int,
    model: str | None = None,
    base_url: str | None = None,
    tool_loop_mode: str | None = None,
    tool_choice: str | dict[str, Any] = "auto",
) -> LLMToolAgentRuntime:
    """Build a runtime for the requested OpenAI-compatible provider."""
    if provider == "deepseek":
        from src.llm.deepseek_client import build_client_from_settings

        llm_client = build_client_from_settings()
    else:
        from src.llm.client import EdgarLLMClient

        if provider == "sglang":
            base_url = base_url or os.environ.get(
                "SGLANG_BASE_URL", "http://localhost:30000/v1"
            )
            model = model or os.environ.get(
                "SGLANG_MODEL", "Qwen/Qwen3.5-35B-A3B"
            )
        elif provider == "vllm":
            base_url = base_url or os.environ.get(
                "VLLM_BASE_URL", "http://localhost:8000/v1"
            )
            model = model or os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
        llm_client = EdgarLLMClient(
            base_url=base_url,
            model=model,
            provider=provider,
            tool_loop_mode=tool_loop_mode,
        )
    return LLMToolAgentRuntime(
        llm_client=llm_client,
        tool_catalog=build_project_tool_catalog(scope=tools_scope),
        max_tool_rounds=max_tool_rounds,
        tool_choice=tool_choice,
    )


def run_research(
    query: str,
    *,
    provider: ProviderChoice = "deepseek",
    tools_scope: ToolScope = "company_research",
    max_tool_rounds: int = 4,
    json_trace_output: str | Path | None = None,
    model: str | None = None,
    base_url: str | None = None,
    tool_loop_mode: str | None = None,
    runtime: LLMToolAgentRuntime | None = None,
) -> dict[str, Any]:
    """Run one tool-loop research query and return a JSON-ready payload."""
    active_runtime = runtime or build_runtime(
        provider=provider,
        tools_scope=tools_scope,
        max_tool_rounds=max_tool_rounds,
        model=model,
        base_url=base_url,
        tool_loop_mode=tool_loop_mode,
    )
    result = active_runtime.run(query)
    payload = result_to_payload(
        result,
        provider=provider,
        tools_scope=tools_scope,
        trace_path=str(json_trace_output) if json_trace_output else None,
    )
    if json_trace_output:
        path = Path(json_trace_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def result_to_payload(
    result: LLMToolRunResult,
    *,
    provider: str,
    tools_scope: str,
    trace_path: str | None,
) -> dict[str, Any]:
    """Convert a runtime result into the CLI/API payload shape."""
    tool_events = [event.model_dump(mode="json") for event in result.tool_events]
    return {
        "provider": provider,
        "tools_scope": tools_scope,
        "mode": result.mode,
        "query": result.goal,
        "final_answer": result.final_answer,
        "tool_calls": [call.model_dump(mode="json") for call in result.tool_calls],
        "tool_events": tool_events,
        "source_urls": sorted(_collect_urls(tool_events)),
        "uncertainty": _extract_uncertainty(result.final_answer),
        "budget_usage": (
            result.budget_usage.model_dump(mode="json")
            if result.budget_usage is not None else None
        ),
        "trace_path": trace_path,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LLM tool-loop research.")
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--provider",
        choices=["deepseek", "vllm", "sglang"],
        default="deepseek",
    )
    parser.add_argument(
        "--tools",
        choices=["company_research", "finrisk_market", "supply_chain"],
        default="company_research",
        dest="tools_scope",
    )
    parser.add_argument("--max-tool-rounds", type=int, default=4)
    parser.add_argument("--json-trace-output", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument(
        "--tool-loop-mode",
        choices=["native", "json_fallback", "auto"],
        default=None,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_research(
        args.query,
        provider=args.provider,
        tools_scope=args.tools_scope,
        max_tool_rounds=args.max_tool_rounds,
        json_trace_output=args.json_trace_output,
        model=args.model,
        base_url=args.base_url,
        tool_loop_mode=args.tool_loop_mode,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _collect_urls(value: Any) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "source_url"} and isinstance(item, str):
                if item.startswith(("http://", "https://")):
                    urls.add(item)
            else:
                urls.update(_collect_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.update(_collect_urls(item))
    elif isinstance(value, str) and value.startswith("{"):
        with suppress(json.JSONDecodeError):
            urls.update(_collect_urls(json.loads(value)))
    return urls


def _extract_uncertainty(text: str) -> str | None:
    lowered = text.lower()
    marker = "uncertainty"
    if marker not in lowered:
        return None
    index = lowered.index(marker)
    return text[index:index + 500].strip()


if __name__ == "__main__":
    raise SystemExit(main())
