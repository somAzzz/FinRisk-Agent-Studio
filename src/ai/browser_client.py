"""Pydantic AI model boundary for the Browser Explorer."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from src.ai.deps import AgentDeps, AgentServices
from src.ai.model_factory import build_agent_model, resolve_agent_model_config
from src.browser.models import BrowserAction, BrowserExplorationOutcome, PageSummary
from src.config import Settings, get_settings
from src.schemas.llm_config import LLMRunConfig

logger = logging.getLogger(__name__)


class BrowserToolSession(Protocol):
    """Guarded browser operations exposed to the Pydantic AI tool loop."""

    async def execute(self, action: BrowserAction) -> dict[str, Any]: ...


@dataclass(slots=True)
class BrowserToolDeps:
    """Typed dependencies for one browser tool-calling run."""

    agent_deps: AgentDeps
    session: BrowserToolSession


class PydanticAIBrowserClient:
    """Run browser summarization and action selection through typed Agents."""

    BLOCKED_URLS = (
        "consent.yahoo.com",
        "google.com/sorry",
        "investor.apple.com",
    )

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.services = services or AgentServices()
        self.conversation_id = conversation_id or f"browser:{uuid.uuid4().hex[:12]}"
        self.summary_agent: Agent[AgentDeps, PageSummary] = Agent(
            model,
            output_type=PageSummary,
            deps_type=AgentDeps,
            instructions=(
                "You are a financial analyst. Summarize only information present "
                "in the supplied page content in two or three sentences."
            ),
            name="browser_page_summarizer",
        )
        self.exploration_agent: Agent[
            BrowserToolDeps, BrowserExplorationOutcome
        ] = Agent(
            model,
            output_type=BrowserExplorationOutcome,
            deps_type=BrowserToolDeps,
            instructions=(
                "You are a web browsing assistant exploring financial news. "
                "Use the browser_action tool to gather evidence. Respect any "
                "stop recommendation returned by the tool and then provide one "
                "typed final outcome. Do not invent URLs or findings."
            ),
            name="browser_explorer",
        )

        @self.exploration_agent.tool
        async def browser_action(
            ctx: RunContext[BrowserToolDeps], action: BrowserAction
        ) -> dict[str, Any]:
            """Execute one bounded, policy-checked browser operation."""
            return await ctx.deps.session.execute(action)

    def _deps(self, run_id: str) -> AgentDeps:
        return AgentDeps(
            run_id=run_id,
            conversation_id=self.conversation_id,
            settings=self.settings,
            services=self.services,
        )

    async def _record(self, *, run_id: str, agent_name: str, result: object) -> None:
        recorder = self.services.message_recorder
        if recorder is not None:
            await recorder.record_result(
                run_id=run_id,
                conversation_id=self.conversation_id,
                agent_name=agent_name,
                result=result,
            )

    async def summarize(self, content: str) -> str:
        """Return a typed page summary, preserving the old bounded fallback."""
        run_id = f"browser-summary-{uuid.uuid4().hex[:12]}"
        try:
            result = await self.summary_agent.run(
                f"Summarize this page:\n\n{content[:5000]}",
                deps=self._deps(run_id),
                run_id=run_id,
                conversation_id=self.conversation_id,
            )
            await self._record(
                run_id=run_id,
                agent_name=self.summary_agent.name or "browser_page_summarizer",
                result=result,
            )
            return result.output.summary
        except Exception as exc:
            logger.info("Browser page summarization failed: %s", exc)
            return content[:200]

    async def explore(
        self,
        *,
        goal: str,
        visited_urls: list[str],
        recent_findings: list[tuple[str, str]],
        session: BrowserToolSession,
        max_steps: int,
    ) -> BrowserExplorationOutcome | None:
        """Let a Pydantic AI Agent own the bounded browser action loop."""
        if max_steps <= 0:
            return BrowserExplorationOutcome(
                summary="The browser step limit was reached.",
                stop_reason="step_limit",
            )
        visited = ", ".join(visited_urls[:5]) or "none"
        findings = "; ".join(
            f"{summary} ({url})" for summary, url in recent_findings[-3:]
        ) or "none"
        blocked = ", ".join(self.BLOCKED_URLS)
        prompt = f"""Goal: {goal}

Visited URLs: {visited}
Recent findings: {findings}
Avoid these verification URLs: {blocked}

You have at most {max_steps} browser operations. Use browser_action with one of
search, navigate, click, scroll, or stop. Start with search when no useful page
has been found. Prefer CNBC and Reuters and skip CAPTCHA or verification pages.
When the tool reports stop_recommended=true, return the final outcome."""
        run_id = f"browser-explore-{uuid.uuid4().hex[:12]}"
        try:
            result = await self.exploration_agent.run(
                prompt,
                deps=BrowserToolDeps(
                    agent_deps=self._deps(run_id),
                    session=session,
                ),
                usage_limits=UsageLimits(
                    request_limit=max_steps + 1,
                    tool_calls_limit=max_steps,
                ),
                run_id=run_id,
                conversation_id=self.conversation_id,
            )
            await self._record(
                run_id=run_id,
                agent_name=self.exploration_agent.name or "browser_explorer",
                result=result,
            )
            return result.output
        except Exception as exc:
            logger.info("Browser exploration tool loop failed: %s", exc)
            return None


def build_browser_client(
    llm_config: LLMRunConfig | None = None,
    *,
    settings: Settings | None = None,
    services: AgentServices | None = None,
) -> PydanticAIBrowserClient:
    """Build the production Browser Explorer client through the model factory."""
    active_settings = settings or get_settings()
    if services is None:
        from src.ai.store_factory import get_agent_run_recorder

        services = AgentServices(message_recorder=get_agent_run_recorder())
    model = build_agent_model(
        resolve_agent_model_config(llm_config, settings=active_settings)
    )
    return PydanticAIBrowserClient(
        model=model,
        settings=active_settings,
        services=services,
    )


__all__ = [
    "BrowserToolDeps",
    "BrowserToolSession",
    "PydanticAIBrowserClient",
    "build_browser_client",
]
