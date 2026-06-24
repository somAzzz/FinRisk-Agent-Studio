"""Step 3: gather recent market evidence for each filing risk.

In demo mode the step reads the fixture's ``market_evidence`` list. In
real mode it would call :class:`SearchRouter`; that integration is left
to a follow-up so this skeleton stays testable without network.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.workflows.state import (
    FinRiskWorkflowState,
    MarketEvidence,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


class MarketExplorerStep(WorkflowStep):
    """Attach ``MarketEvidence`` rows to ``filing_risks``.

    The step intentionally avoids running a real search in the skeleton:
    the goal is to verify the contract and shape. Real LLM-driven
    exploration is layered on top in a follow-up.
    """

    name = "market_explorer"

    def __init__(
        self,
        fixture_loader=None,
        search_router=None,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._router_factory = search_router
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
            evidence = await self._explore_live(state)

        # Only attach evidence relevant to a known risk_id (or general).
        valid_ids = {r.risk_id for r in state.filing_risks}
        kept: list[MarketEvidence] = []
        for ev in evidence:
            if ev.risk_id is None or ev.risk_id in valid_ids:
                kept.append(ev)
        state.market_evidence = kept
        return state

    async def _explore_live(self, state: FinRiskWorkflowState) -> list[MarketEvidence]:
        """Real-mode market exploration.

        Uses the existing :class:`SearchRouter` when a router is
        injected; otherwise returns an empty list so the workflow
        continues without market evidence.
        """
        router = self._router_factory() if self._router_factory else None
        if router is None:
            return []
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
            return collected
        except Exception as exc:
            logger.info("MarketExplorer live search failed: %s", exc)
            return []


def _default_fixture_loader(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["DEMO_FIXTURE_PATH", "MarketExplorerStep"]