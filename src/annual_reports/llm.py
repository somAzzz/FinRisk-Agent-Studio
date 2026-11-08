"""Run typed document research through the configured Pydantic AI provider."""

import json
from collections.abc import Callable

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.messages import ModelResponse
from pydantic_ai.settings import ModelSettings

from src.ai import model_factory


def run_structured[T: BaseModel](
    output_type: type[T],
    instructions: str,
    prompt: str,
    *,
    max_tokens: int,
    timeout: int,
    validate: Callable[[T], None],
) -> T:
    config = model_factory.resolve_agent_model_config()
    local = config.provider in {"sglang", "vllm"}
    settings: ModelSettings = {"temperature": 0, "max_tokens": max_tokens, "timeout": timeout}
    if config.provider == "sglang":
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    if local:
        instructions += "\nReturn one JSON object matching this schema: " + json.dumps(output_type.model_json_schema())
    agent = Agent(
        model_factory.build_agent_model(config),
        output_type=NativeOutput(output_type, template=False) if local else output_type,
        instructions=instructions,
        retries=1 if local else 2,
        model_settings=settings,
    )

    @agent.output_validator
    async def check(ctx: RunContext, output: T) -> T:
        response = next((m for m in reversed(ctx.messages) if isinstance(m, ModelResponse)), None)
        if response and response.finish_reason in {"length", "content_filter", "error"}:
            raise ModelRetry("Return the complete structured response.")
        try:
            validate(output)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        return output

    return agent.run_sync(prompt).output
