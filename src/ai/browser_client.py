"""Pydantic AI model boundary for the Browser Explorer."""

from __future__ import annotations

import logging
import uuid

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.ai.deps import AgentDeps, AgentServices
from src.ai.model_factory import build_agent_model, resolve_agent_model_config
from src.browser.models import BrowserAction, PageSummary
from src.config import Settings, get_settings
from src.schemas.llm_config import LLMRunConfig

logger = logging.getLogger(__name__)


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
        self.action_agent: Agent[AgentDeps, BrowserAction] = Agent(
            model,
            output_type=BrowserAction,
            deps_type=AgentDeps,
            instructions=(
                "You are a web browsing assistant exploring financial news. "
                "Select exactly one typed browser action and do not invent URLs."
            ),
            name="browser_action_selector",
        )

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

    async def decide_action(
        self,
        goal: str,
        visited_urls: list[str],
        recent_findings: list[tuple[str, str]],
    ) -> BrowserAction | None:
        """Select the next browser action as validated Pydantic output."""
        visited = ", ".join(visited_urls[:5]) or "none"
        findings = "; ".join(
            f"{summary} ({url})" for summary, url in recent_findings[-3:]
        ) or "none"
        blocked = ", ".join(self.BLOCKED_URLS)
        prompt = f"""Goal: {goal}

Visited URLs: {visited}
Recent findings: {findings}
Avoid these verification URLs: {blocked}

Use search to discover relevant pages, navigate or click to inspect them, scroll
when more content is needed, and stop when enough evidence has been gathered.
Prefer CNBC and Reuters search pages and skip CAPTCHA or verification pages."""
        run_id = f"browser-action-{uuid.uuid4().hex[:12]}"
        try:
            result = await self.action_agent.run(
                prompt,
                deps=self._deps(run_id),
                run_id=run_id,
                conversation_id=self.conversation_id,
            )
            await self._record(
                run_id=run_id,
                agent_name=self.action_agent.name or "browser_action_selector",
                result=result,
            )
            return result.output
        except Exception as exc:
            logger.info("Browser action selection failed: %s", exc)
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


__all__ = ["PydanticAIBrowserClient", "build_browser_client"]
