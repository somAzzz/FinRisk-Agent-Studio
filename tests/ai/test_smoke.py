"""Side-effect-free Pydantic AI Agent smoke test."""

from pydantic_ai.models.test import TestModel

from src.ai.deps import AgentDeps
from src.ai.smoke import build_smoke_agent
from src.config import Settings


def test_smoke_agent_returns_typed_output() -> None:
    model = TestModel(
        custom_output_args={"status": "ok", "message": "runtime ready"}
    )
    agent = build_smoke_agent(model)

    result = agent.run_sync(
        "Check the runtime.",
        deps=AgentDeps(run_id="smoke-1", settings=Settings()),
    )

    assert result.output.status == "ok"
    assert result.output.message == "runtime ready"
