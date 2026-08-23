"""Sequential parity tests for the FinRisk Pydantic Graph."""

from pathlib import Path

from src.ai.graphs.finrisk import run_finrisk_graph
from src.workflows.finrisk_workflow import run_finrisk_workflow
from src.workflows.state import FinRiskRequest, FinRiskWorkflowState

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


def _request() -> FinRiskRequest:
    return FinRiskRequest(
        ticker="AAPL",
        company_name="Apple Inc.",
        analysis_goal="Identify current financial and supply-chain risks.",
        year=2024,
        demo_mode=True,
    )


async def test_finrisk_graph_matches_sequential_demo_contract() -> None:
    legacy_initial = FinRiskWorkflowState(
        run_id="parity-finrisk", request=_request()
    )
    graph_initial = FinRiskWorkflowState(
        run_id="parity-finrisk", request=_request()
    )

    legacy = await run_finrisk_workflow(
        _request(), fixture_path=FIXTURE, initial_state=legacy_initial
    )
    graph = await run_finrisk_graph(
        _request(), fixture_path=FIXTURE, initial_state=graph_initial
    )

    assert graph.status == legacy.status == "completed"
    assert [event.step_name for event in graph.trace] == [
        event.step_name for event in legacy.trace
    ]
    assert [event.status for event in graph.trace] == [
        event.status for event in legacy.trace
    ]
    assert graph.company is not None and legacy.company is not None
    assert graph.company.ticker == legacy.company.ticker
    assert graph.company.cik == legacy.company.cik
    assert [risk.risk_id for risk in graph.filing_risks] == [
        risk.risk_id for risk in legacy.filing_risks
    ]
    assert [item.evidence_id for item in graph.market_evidence] == [
        item.evidence_id for item in legacy.market_evidence
    ]
    assert [item.evidence_id for item in graph.normalized_evidence] == [
        item.evidence_id for item in legacy.normalized_evidence
    ]
    assert [item.risk_id for item in graph.risk_scores] == [
        item.risk_id for item in legacy.risk_scores
    ]
    assert graph.report is not None and legacy.report is not None
    assert graph.report.markdown == legacy.report.markdown
    FinRiskWorkflowState.model_validate(graph.model_dump(mode="json"))
