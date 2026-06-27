"""Step 3: gather recent market evidence for each filing risk.

In demo mode the step reads the fixture's ``market_evidence`` list. In
real mode it uses a :class:`SearchRouter` (auto-constructed if none
is injected) and writes a :class:`FallbackEvent` to the state when
the search raises. The v17 audit added a default-router fallback so
the step never silently returns an empty list.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.evaluation.models import FallbackEvent
from src.schemas.tool_trace import ToolLoopTrace
from src.workflows.state import (
    FinRiskWorkflowState,
    MarketEvidence,
    utcnow,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


class MarketExplorerStep(WorkflowStep):
    """Attach ``MarketEvidence`` rows to ``filing_risks``.

    In demo mode the fixture is read directly. In real mode the
    step constructs a default :class:`SearchRouter` when none was
    injected; search failures are converted to ``FallbackEvent``
    rows on the state so downstream steps can react.
    """

    name = "market_explorer"

    def __init__(
        self,
        fixture_loader=None,
        search_router=None,
        llm_runtime_factory=None,
        llm_shadow_mode: bool = False,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._router_factory = search_router
        self._llm_runtime_factory = llm_runtime_factory
        self._llm_shadow_mode = llm_shadow_mode
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        request = state.request
        if request.demo_mode or request.cached_mode:
            data = self._load_fixture(self._fixture_path)
            evidence = [
                MarketEvidence.model_validate(item)
                for item in data.get("market_evidence", [])
            ]
        else:
            evidence, fallback = await self._explore_live(state)
            if fallback is not None:
                state.fallback_events.append(fallback)
            if self._llm_shadow_mode:
                shadow_fallback = self._run_llm_shadow(state)
                if shadow_fallback is not None:
                    state.fallback_events.append(shadow_fallback)

        # Only attach evidence relevant to a known risk_id (or general).
        valid_ids = {r.risk_id for r in state.filing_risks}
        kept: list[MarketEvidence] = []
        for ev in evidence:
            if ev.risk_id is None or ev.risk_id in valid_ids:
                kept.append(ev)
        state.market_evidence = kept
        return state

    async def _explore_live(
        self, state: FinRiskWorkflowState
    ) -> tuple[list[MarketEvidence], FallbackEvent | None]:
        """Real-mode market exploration.

        Returns a ``(evidence, fallback_event)`` tuple. The fallback
        event is non-None whenever the search failed; the workflow
        can then continue with whatever the search did return.
        """
        router = self._default_router()
        if router is None:
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="live",
                to_mode="cached",
                reason="no SearchRouter available; skipping market evidence",
                occurred_at=utcnow(),
            )
        try:
            from src.tools.search_router import to_evidence

            collected: list[MarketEvidence] = []
            for risk in state.filing_risks:
                response = router.search(
                    risk.risk_factor, intent="supply_chain", ttl_seconds=60
                )
                if not response.results:
                    continue
                legacy = to_evidence(response)
                collected.append(
                    MarketEvidence(
                        evidence_id=f"market-{legacy.evidence_id}",
                        risk_id=risk.risk_id,
                        source_url=legacy.url or "https://example.com/",
                        source_title=legacy.title,
                        source_type="news",
                        claim=legacy.quote,
                        evidence_summary=legacy.quote,
                        supports_risk=True,
                        contradicts_risk=False,
                        confidence=legacy.confidence,
                        timestamp=legacy.retrieved_at,
                    )
                )
            return collected, None
        except Exception as exc:
            logger.info("MarketExplorer live search failed: %s", exc)
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="live",
                to_mode="cached",
                reason=f"SearchRouter raised {type(exc).__name__}: {exc}",
                occurred_at=utcnow(),
            )

    def _run_llm_shadow(self, state: FinRiskWorkflowState) -> FallbackEvent | None:
        """Run LLM-driven market exploration in shadow mode.

        Shadow mode records LLM/tool traces but never changes
        ``state.market_evidence``. This lets us compare the new tool loop
        against the deterministic SearchRouter path before making it primary.
        """
        runtime = self._default_llm_runtime()
        if runtime is None:
            return FallbackEvent(
                step_name=self.name,
                from_mode="llm_shadow",
                to_mode="deterministic",
                reason="no LLMToolAgentRuntime available for market shadow mode",
                occurred_at=utcnow(),
            )
        try:
            for risk in state.filing_risks:
                goal = _shadow_goal(state, risk)
                result = runtime.run(goal)
                state.llm_log.extend(result.llm_calls)
                state.tool_traces.append(
                    ToolLoopTrace(
                        mode=result.mode,
                        tool_events=result.tool_events,
                        budget_usage=result.budget_usage,
                    )
                )
            return None
        except Exception as exc:
            logger.info("MarketExplorer LLM shadow failed: %s", exc)
            return FallbackEvent(
                step_name=self.name,
                from_mode="llm_shadow",
                to_mode="deterministic",
                reason=f"LLM shadow raised {type(exc).__name__}: {exc}",
                occurred_at=utcnow(),
            )

    def _default_router(self) -> Any | None:
        """Resolve the router used in real mode.

        Order:
        1. Caller-supplied ``_router_factory``.
        2. Auto-constructed :class:`SearchRouter` from
           ``src.tools.search_router``.
        3. ``None`` when the router cannot be imported (e.g. a slim
           install without the search dependencies).
        """
        if self._router_factory is not None:
            try:
                return self._router_factory()
            except Exception:
                return None
        try:
            from src.tools.search_router import SearchRouter

            return SearchRouter()
        except Exception:
            return None

    def _default_llm_runtime(self) -> Any | None:
        if self._llm_runtime_factory is not None:
            try:
                return self._llm_runtime_factory()
            except Exception:
                return None
        try:
            from src.agents.llm_runtime import LLMToolAgentRuntime
            from src.llm.deepseek_client import build_client_from_settings
            from src.tools.catalog import build_project_tool_catalog

            return LLMToolAgentRuntime(
                llm_client=build_client_from_settings(),
                tool_catalog=build_project_tool_catalog(scope="finrisk_market"),
            )
        except Exception:
            return None


def _default_fixture_loader(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _shadow_goal(state: FinRiskWorkflowState, risk: Any) -> str:
    ticker = state.request.ticker
    company = state.company.company_name if state.company else state.request.company_name
    company_part = f"{company} ({ticker})" if company else ticker
    return (
        "Collect recent market evidence for a financial risk. "
        "Use read-only tools only. Return evidence, inference, uncertainty, "
        "and suggested next checks. "
        f"Company: {company_part}. "
        f"Risk: {risk.risk_factor}. "
        f"Time horizon: {state.request.time_horizon}."
    )


__all__ = ["DEMO_FIXTURE_PATH", "MarketExplorerStep"]
