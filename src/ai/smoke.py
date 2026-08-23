"""Side-effect-free smoke Agent used to verify the Pydantic AI boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.ai.deps import AgentDeps


class SmokeAgentOutput(BaseModel):
    """Typed output proving model, deps and validation are connected."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    message: str


def build_smoke_agent(model: Model) -> Agent[AgentDeps, SmokeAgentOutput]:
    """Create a smoke Agent that has no tools and no external side effects."""
    return Agent(
        model,
        output_type=SmokeAgentOutput,
        deps_type=AgentDeps,
        instructions=(
            "Return status='ok' and a short readiness message. "
            "Do not call tools or access external systems."
        ),
        name="finrisk_pydantic_ai_smoke",
    )


__all__ = ["SmokeAgentOutput", "build_smoke_agent"]
