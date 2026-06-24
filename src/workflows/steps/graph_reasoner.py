"""Step 6: graph-based second-order effects."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.workflows.state import (
    FinRiskWorkflowState,
    GraphInsight,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


class GraphReasonerStep(WorkflowStep):
    """Emit ``GraphInsight`` rows.

    In demo mode the step reads from the fixture. In real mode it
    delegates to the existing :class:`src.agents.graph_agent.GraphReasoningAgent`,
    falling back to the fixture when Neo4j is unavailable.
    """

    name = "graph_reasoner"

    def __init__(
        self,
        fixture_loader=None,
        graph_client=None,
        graph_agent_factory=None,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._graph_client = graph_client
        self._graph_agent_factory = graph_agent_factory
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        request = state.request
        company = state.company.company_name if state.company else ""

        if request.demo_mode or request.cached_mode:
            data = self._load_fixture(self._fixture_path)
            insights = [
                GraphInsight.model_validate(item)
                for item in data.get("graph_insights", [])
            ]
        else:
            insights = self._reason_live(state, company)

        # Translate raw IDs (risk_id, market evidence_id) into the
        # normalized evidence_id space so the report and the
        # ``supporting_evidence_ids`` guardrail reference the same
        # evidence table rows.
        normalized = self._translate_supporting_ids(insights, state)
        state.graph_insights = normalized
        return state

    @staticmethod
    def _translate_supporting_ids(
        insights: list[GraphInsight], state: FinRiskWorkflowState
    ) -> list[GraphInsight]:
        raw_to_normalized: dict[str, str] = {}
        for risk in state.filing_risks:
            raw_to_normalized[risk.risk_id] = f"ne-{risk.risk_id}"
        for ev in state.market_evidence:
            raw_to_normalized[ev.evidence_id] = f"ne-{ev.evidence_id}"
        result: list[GraphInsight] = []
        for ins in insights:
            translated = [
                raw_to_normalized.get(eid, eid) for eid in ins.supporting_evidence_ids
            ]
            result.append(ins.model_copy(update={"supporting_evidence_ids": translated}))
        return result

    def _reason_live(
        self,
        state: FinRiskWorkflowState,
        company: str,
    ) -> list[GraphInsight]:
        """Try the real GraphReasoningAgent; fall back to fixture on error."""
        try:
            from src.agents.graph_agent import GraphReasoningAgent

            factory = self._graph_agent_factory or GraphReasoningAgent
            agent = factory(client=self._graph_client)
            from src.agents.state import AgentState

            inner = AgentState(goal=state.request.analysis_goal, ticker=state.request.ticker)
            agent.run(inner)
            # Convert any notes about paths into typed insights if they
            # look like upstream paths. This keeps the skeleton useful
            # even without a real graph.
            insights: list[GraphInsight] = []
            for note in inner.notes:
                if "upstream path" not in note:
                    continue
                # Format: "graph: upstream path for AAPL: A -> B -> C"
                parts = note.split(": ", 2)
                if len(parts) < 3:
                    continue
                path = parts[2]
                nodes = [n.strip() for n in path.split("->")]
                if len(nodes) < 2:
                    continue
                insights.append(
                    GraphInsight(
                        insight_id=f"g-live-{len(insights) + 1:03d}",
                        source_company=company or state.request.ticker,
                        affected_entity=nodes[-1],
                        risk_path=nodes,
                        investment_theme=None,
                        supporting_evidence_ids=[
                            f"ne-{r.risk_id}" for r in state.filing_risks[:3]
                        ],
                        confidence=0.6,
                    )
                )
            return insights
        except Exception as exc:  # noqa: BLE001
            logger.info("GraphReasoner live failed, falling back: %s", exc)
            return self._reason_live_fallback(state, company)

    def _reason_live_fallback(
        self,
        state: FinRiskWorkflowState,
        company: str,
    ) -> list[GraphInsight]:
        """If a Neo4j client is missing, build a minimal path from filing risks."""
        if not state.filing_risks:
            return []
        risk = state.filing_risks[0]
        return [
            GraphInsight(
                insight_id="g-fallback-001",
                source_company=company or state.request.ticker,
                affected_entity=risk.risk_factor[:60],
                risk_path=[company or state.request.ticker, risk.risk_type],
                supporting_evidence_ids=[f"ne-{risk.risk_id}"],
                confidence=0.4,
            )
        ]


def _default_fixture_loader(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["GraphReasonerStep", "DEMO_FIXTURE_PATH"]