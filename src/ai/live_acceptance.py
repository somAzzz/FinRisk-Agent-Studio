"""Minimal live-provider contract for the Pydantic AI migration gate."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models import Model


class LiveAcceptanceOutput(BaseModel):
    """Typed payload the provider must return after the local probe."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    observed_value: int


class LiveAcceptanceReport(BaseModel):
    """Machine-readable proof of model, tool-call and output compatibility."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    base_url: str
    model: str
    output_valid: bool
    local_tool_calls: int
    requests: int
    input_tokens: int
    output_tokens: int


async def run_live_acceptance(
    *,
    provider: str,
    base_url: str,
    model_name: str,
    model: Model,
) -> LiveAcceptanceReport:
    """Run one synthetic typed-output request with one harmless local tool."""
    observed_calls: list[int] = []
    agent = Agent(
        model,
        output_type=LiveAcceptanceOutput,
        instructions=(
            "This is a provider contract test. Call local_probe exactly once "
            "with value 7, then return status='ok' and observed_value=7."
        ),
        name="finrisk_pydantic_ai_live_acceptance",
    )

    @agent.tool_plain
    async def local_probe(value: int) -> int:
        """Return a harmless integer without reading project or user data."""
        observed_calls.append(value)
        return value

    result = await agent.run(
        "Run the synthetic provider contract test.",
        usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1),
    )
    output = result.output
    if output.status != "ok" or output.observed_value != 7:
        raise ValueError("provider returned an invalid typed acceptance payload")
    if observed_calls != [7]:
        raise ValueError(
            f"local_probe must be called exactly once with 7; got {observed_calls!r}"
        )
    usage_value = result.usage
    usage = usage_value() if callable(usage_value) else usage_value
    return LiveAcceptanceReport(
        provider=provider,
        base_url=base_url,
        model=model_name,
        output_valid=True,
        local_tool_calls=len(observed_calls),
        requests=usage.requests,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )


__all__ = [
    "LiveAcceptanceOutput",
    "LiveAcceptanceReport",
    "run_live_acceptance",
]
