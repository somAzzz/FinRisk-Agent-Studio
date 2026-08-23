"""CLI runner for real-case Pydantic AI tool-enabled research.

Example:

    uv run python -m src.pipelines.llm_tool_research \
      --provider deepseek \
      --tools finrisk_market \
      --query "Find evidence about Apple's supply chain risk."
"""

from __future__ import annotations

import argparse
import json
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

from src.agents.state import AgentBudget
from src.ai import model_factory
from src.ai.deps import AgentDeps, AgentPermissions, AgentServices, AgentSubject
from src.ai.runtime_adapter import PydanticAIRuntimeAdapter
from src.ai.runtime_types import DEFAULT_SYSTEM_PROMPT, LLMToolRunResult
from src.config import get_settings
from src.schemas.llm_config import LLMRunConfig
from src.tools.catalog import build_project_tool_catalog

ProviderChoice = Literal["deepseek", "openai", "sglang", "vllm"]
ToolScope = Literal["company_research", "finrisk_market", "supply_chain"]


def build_runtime(
    *,
    provider: ProviderChoice,
    tools_scope: ToolScope,
    max_tool_rounds: int,
    model: str | None = None,
    base_url: str | None = None,
) -> PydanticAIRuntimeAdapter:
    """Build a Pydantic AI runtime for the requested OpenAI-compatible provider."""
    settings = get_settings()
    agent_model = model_factory.build_agent_model(
        model_factory.resolve_agent_model_config(
            LLMRunConfig(
                provider=provider,
                base_url=base_url,
                model=model,
            ),
            settings=settings,
        )
    )
    run_id = f"llm-tool-research-{uuid.uuid4().hex[:12]}"
    deps = AgentDeps(
        run_id=run_id,
        conversation_id=run_id,
        settings=settings,
        subject=AgentSubject(),
        permissions=AgentPermissions(
            tool_scopes=frozenset({tools_scope}),
            allow_interactive=False,
            allow_write=False,
        ),
        budget=AgentBudget(
            max_tool_rounds_per_subgoal=max_tool_rounds,
        ),
        services=AgentServices(
            tool_catalog=build_project_tool_catalog(scope=tools_scope),
        ),
    )
    return PydanticAIRuntimeAdapter(
        model=agent_model,
        deps=deps,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
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
    runtime: PydanticAIRuntimeAdapter | None = None,
) -> dict[str, Any]:
    """Run one tool-enabled research query and return a JSON-ready payload."""
    active_runtime = runtime or build_runtime(
        provider=provider,
        tools_scope=tools_scope,
        max_tool_rounds=max_tool_rounds,
        model=model,
        base_url=base_url,
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
    parser = argparse.ArgumentParser(description="Run Pydantic AI research.")
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--provider",
        choices=["deepseek", "openai", "sglang", "vllm"],
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
