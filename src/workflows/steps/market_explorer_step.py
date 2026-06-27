"""Step 3: gather recent market evidence for each filing risk.

In demo mode the step reads the fixture's ``market_evidence`` list. In
real mode it uses a :class:`SearchRouter` (auto-constructed if none
is injected) and writes a :class:`FallbackEvent` to the state when
the search raises. The v17 audit added a default-router fallback so
the step never silently returns an empty list.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.evaluation.models import FallbackEvent
from src.schemas.tool_trace import ToolLoopTrace
from src.workflows.state import (
    ExtractedRisk,
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
        llm_mode: str = "deterministic",
        llm_shadow_mode: bool = False,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._router_factory = search_router
        self._llm_runtime_factory = llm_runtime_factory
        self._llm_mode = "shadow" if llm_shadow_mode else llm_mode
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        request = state.request
        if request.demo_mode or request.cached_mode:
            data = self._load_fixture(self._fixture_path)
            evidence = [
                MarketEvidence.model_validate(item)
                for item in data.get("market_evidence", [])
            ]
        elif self._llm_mode == "primary":
            evidence, fallback = self._explore_llm_primary(state)
            if fallback is not None:
                state.fallback_events.append(fallback)
            if not evidence:
                evidence, deterministic_fallback = await self._explore_live(state)
                if deterministic_fallback is not None:
                    state.fallback_events.append(deterministic_fallback)
        else:
            evidence, fallback = await self._explore_live(state)
            if fallback is not None:
                state.fallback_events.append(fallback)
            if self._llm_mode == "shadow":
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

    def _explore_llm_primary(
        self, state: FinRiskWorkflowState
    ) -> tuple[list[MarketEvidence], FallbackEvent | None]:
        """Use the LLM tool loop as the primary market evidence collector."""
        runtime = self._default_llm_runtime()
        if runtime is None:
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="llm_primary",
                to_mode="deterministic",
                reason="no LLMToolAgentRuntime available for market primary mode",
                occurred_at=utcnow(),
            )

        collected: list[MarketEvidence] = []
        try:
            for risk in state.filing_risks:
                result = runtime.run(_shadow_goal(state, risk))
                state.llm_log.extend(result.llm_calls)
                state.tool_traces.append(
                    ToolLoopTrace(
                        mode=result.mode,
                        tool_events=result.tool_events,
                        budget_usage=result.budget_usage,
                    )
                )
                collected.extend(_market_evidence_from_tool_events(risk, result))
        except Exception as exc:
            logger.info("MarketExplorer LLM primary failed: %s", exc)
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="llm_primary",
                to_mode="deterministic",
                reason=f"LLM primary raised {type(exc).__name__}: {exc}",
                occurred_at=utcnow(),
            )

        if not collected:
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="llm_primary",
                to_mode="deterministic",
                reason="LLM primary produced no source-backed market evidence",
                occurred_at=utcnow(),
            )
        return collected, None

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


def _market_evidence_from_tool_events(
    risk: ExtractedRisk,
    result: Any,
) -> list[MarketEvidence]:
    evidence: list[MarketEvidence] = []
    for event in result.tool_events:
        if event.status != "success":
            continue
        payload = _parse_tool_payload(event.result_summary)
        if not payload:
            continue
        data = payload.get("data", payload)
        tool_name = payload.get("tool", event.tool_name)
        if tool_name == "web_search":
            evidence.extend(_evidence_from_search_data(risk, data, event.event_id))
        elif tool_name == "search_and_fetch":
            search = data.get("search", {}) if isinstance(data, dict) else {}
            evidence.extend(_evidence_from_search_data(risk, search, event.event_id))
            evidence.extend(_evidence_from_fetched_pages(risk, data, event.event_id))
        elif tool_name == "web_fetch":
            item = _evidence_from_fetch_data(risk, data, event.event_id)
            if item is not None:
                evidence.append(item)
        elif tool_name == "transcript_lookup":
            item = _evidence_from_transcript_data(risk, data, event.event_id)
            if item is not None:
                evidence.append(item)
    return evidence


def _parse_tool_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _evidence_from_search_data(
    risk: ExtractedRisk,
    data: Any,
    event_id: str,
) -> list[MarketEvidence]:
    if not isinstance(data, dict):
        return []
    timestamp = _parse_timestamp(data.get("retrieved_at"))
    out: list[MarketEvidence] = []
    for index, row in enumerate(data.get("results", []) or []):
        if not isinstance(row, dict):
            continue
        snippet = str(row.get("snippet") or "").strip()
        url = str(row.get("url") or "").strip()
        if not snippet or not _is_http_url(url):
            continue
        source_type = _market_source_type(url, fallback="news")
        confidence = _source_confidence(source_type, snippet)
        if confidence < 0.5:
            continue
        out.append(
            MarketEvidence(
                evidence_id=f"llm-{event_id}-{index}",
                risk_id=risk.risk_id,
                source_url=url,
                source_title=row.get("title"),
                source_type=source_type,
                claim=snippet,
                evidence_summary=snippet,
                supports_risk=True,
                contradicts_risk=False,
                confidence=confidence,
                timestamp=_parse_timestamp(row.get("published_at")) or timestamp,
            )
        )
    return out


def _evidence_from_fetched_pages(
    risk: ExtractedRisk,
    data: Any,
    event_id: str,
) -> list[MarketEvidence]:
    if not isinstance(data, dict):
        return []
    pages = data.get("fetched_pages", []) or []
    out: list[MarketEvidence] = []
    for index, page in enumerate(pages):
        item = _evidence_from_fetch_data(risk, page, f"{event_id}-fetch-{index}")
        if item is not None:
            out.append(item)
    return out


def _evidence_from_fetch_data(
    risk: ExtractedRisk,
    data: Any,
    event_id: str,
) -> MarketEvidence | None:
    if not isinstance(data, dict):
        return None
    if data.get("status") not in {None, "success"}:
        return None
    url = str(data.get("url") or "").strip()
    content = str(data.get("content") or data.get("description") or "").strip()
    if not content or not _is_http_url(url):
        return None
    summary = _compact_text(content)
    source_type = _market_source_type(url, fallback="company")
    confidence = _source_confidence(source_type, summary)
    if confidence < 0.5:
        return None
    return MarketEvidence(
        evidence_id=f"llm-{event_id}",
        risk_id=risk.risk_id,
        source_url=url,
        source_title=data.get("title"),
        source_type=source_type,
        claim=summary,
        evidence_summary=summary,
        supports_risk=True,
        contradicts_risk=False,
        confidence=confidence,
        timestamp=_parse_timestamp(data.get("fetched_at")),
    )


def _evidence_from_transcript_data(
    risk: ExtractedRisk,
    data: Any,
    event_id: str,
) -> MarketEvidence | None:
    if not isinstance(data, dict):
        return None
    url = str(data.get("url") or "").strip()
    if not _is_http_url(url):
        return None
    turns = data.get("turns", []) or []
    snippets = []
    for turn in turns[:3]:
        if isinstance(turn, dict):
            snippets.append(str(turn.get("text") or turn.get("content") or "").strip())
    summary = _compact_text(" ".join(part for part in snippets if part))
    if not summary:
        return None
    return MarketEvidence(
        evidence_id=f"llm-{event_id}",
        risk_id=risk.risk_id,
        source_url=url,
        source_title=data.get("title"),
        source_type="transcript",
        claim=summary,
        evidence_summary=summary,
        supports_risk=True,
        contradicts_risk=False,
        confidence=0.8,
        timestamp=_parse_timestamp(data.get("published_at")),
    )


def _parse_timestamp(value: Any) -> Any:
    if not value:
        return utcnow()
    if hasattr(value, "tzinfo"):
        return value
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=utcnow().tzinfo)
    except ValueError:
        return utcnow()


def _is_http_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def _market_source_type(url: str, *, fallback: str) -> str:
    host = urlparse(url).netloc.lower()
    if "sec.gov" in host:
        return "filing"
    if host.endswith(".gov") or "federalregister.gov" in host:
        return "regulatory"
    if any(domain in host for domain in ("apple.com", "microsoft.com", "nvidia.com")):
        return "company"
    if any(domain in host for domain in ("reuters.com", "bloomberg.com", "wsj.com")):
        return "financial"
    return fallback


def _source_confidence(source_type: str, text: str) -> float:
    base = {
        "filing": 0.9,
        "regulatory": 0.9,
        "company": 0.8,
        "financial": 0.75,
        "transcript": 0.8,
        "news": 0.65,
        "other": 0.45,
    }.get(source_type, 0.45)
    if len(text) < 40:
        base -= 0.15
    return max(0.0, min(1.0, base))


def _compact_text(text: str, limit: int = 600) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


__all__ = ["DEMO_FIXTURE_PATH", "MarketExplorerStep"]
