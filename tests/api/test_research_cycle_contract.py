from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.research import (
    set_company_research_orchestrator_for_tests,
    set_expectation_store_for_tests,
    set_peer_group_store_for_tests,
    set_research_alert_store_for_tests,
    set_research_change_store_for_tests,
    set_research_journal_store_for_tests,
    set_research_snapshot_store_for_tests,
    set_valuation_assumption_store_for_tests,
)
from src.research.alert_store import ResearchAlertStore
from src.research.change_store import ResearchChangeStore
from src.research.expectations import ExpectationStore
from src.research.journal import ResearchJournalStore
from src.research.models import FinancialMetricPoint, FinancialSnapshot
from src.research.orchestrator import CompanyResearchOrchestrator
from src.research.peer_groups import PeerGroupStore
from src.research.snapshot_store import ResearchSnapshotStore
from src.research.valuation_store import ValuationAssumptionStore


def _financials(ticker: str, as_of: date | None) -> FinancialSnapshot:
    selected = as_of or date.today()
    return FinancialSnapshot(
        ticker=ticker,
        cik="1",
        as_of=datetime(selected.year, selected.month, selected.day, tzinfo=UTC),
        metrics=[
            FinancialMetricPoint(
                metric="revenue",
                value=100 if selected.year == 2025 else 120,
                unit="USD",
                period_end=date(selected.year, 3, 31),
                period_kind="quarter",
                fiscal_year=selected.year,
                fiscal_period="Q1",
                filed_at=date(selected.year, 4, 20),
                source_concept="Revenue",
                accession_number=f"filing-{selected.year}",
            )
        ],
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    database = tmp_path / "research.sqlite"
    snapshots = ResearchSnapshotStore(database)
    set_research_snapshot_store_for_tests(snapshots)
    set_company_research_orchestrator_for_tests(
        CompanyResearchOrchestrator(
            store=snapshots,
            financial_loader=_financials,
        )
    )
    set_research_change_store_for_tests(ResearchChangeStore(database))
    set_research_alert_store_for_tests(ResearchAlertStore(database))
    set_expectation_store_for_tests(ExpectationStore(database))
    set_research_journal_store_for_tests(ResearchJournalStore(database))
    set_peer_group_store_for_tests(PeerGroupStore(database))
    set_valuation_assumption_store_for_tests(ValuationAssumptionStore(database))
    yield TestClient(app)
    set_company_research_orchestrator_for_tests(None)
    set_research_snapshot_store_for_tests(None)
    set_research_change_store_for_tests(None)
    set_research_alert_store_for_tests(None)
    set_expectation_store_for_tests(None)
    set_research_journal_store_for_tests(None)
    set_peer_group_store_for_tests(None)
    set_valuation_assumption_store_for_tests(None)


def test_research_snapshot_change_expectation_and_sensitivity_contract(client) -> None:
    old = client.post(
        "/research/runs",
        json={
            "ticker": "ACME",
            "as_of": "2025-04-30",
            "include_management": False,
            "include_risks": False,
        },
    )
    new = client.post(
        "/research/runs",
        json={
            "ticker": "ACME",
            "as_of": "2026-04-30",
            "include_management": False,
            "include_risks": False,
        },
    )
    assert old.status_code == 201
    assert new.status_code == 201
    old_id = old.json()["snapshot"]["snapshot_id"]
    new_id = new.json()["snapshot"]["snapshot_id"]

    changes = client.get(
        "/research/changes/ACME",
        params={"from_snapshot_id": old_id, "to_snapshot_id": new_id},
    )
    assert changes.status_code == 200
    assert changes.json()["changes"][0]["materiality"] == "high"

    expectation = client.post(
        "/research/expectations",
        json={
            "ticker": "ACME",
            "metric": "revenue",
            "fiscal_period": "2026Q1",
            "value": 110,
            "unit": "USD",
            "source": "personal model",
            "origin": "user",
            "observed_at": "2026-03-01T00:00:00Z",
            "as_of": "2026-03-01T00:00:00Z",
        },
    )
    assert expectation.status_code == 201
    comparison = client.get(
        f"/research/expectations/{expectation.json()['expectation_id']}/compare",
        params={"snapshot_id": new_id},
    )
    assert comparison.status_code == 200
    assert comparison.json()["absolute_surprise"] == 10

    sensitivity = client.post(
        "/research/valuation/sensitivity",
        json={
            "ticker": "ACME",
            "kind": "growth_margin",
            "base_revenue": 1000,
            "net_debt": 100,
            "diluted_shares": 100,
            "forecast_years": 1,
            "fixed_multiple": 10,
            "row_values": [0, 0.1],
            "column_values": [0.1, 0.2],
        },
    )
    assert sensitivity.status_code == 200
    assert len(sensitivity.json()["cells"]) == 4
    assumption_id = sensitivity.json()["assumption_snapshot_id"]
    assert assumption_id.startswith("valuation-")
    history = client.get("/research/valuation/history/ACME")
    assert history.status_code == 200
    assert history.json()[0]["assumption_snapshot_id"] == assumption_id


def test_peer_group_contract_requires_confirmed_members(client) -> None:
    response = client.post(
        "/research/peer-groups",
        json={
            "name": "Semiconductors",
            "base_ticker": "NVDA",
            "industry_template": "semiconductor",
            "members": [
                {"ticker": "NVDA", "inclusion_reason": "Base company"},
                {"ticker": "AMD", "inclusion_reason": "Accelerator peer"},
            ],
        },
    )

    assert response.status_code == 201
    listed = client.get("/research/peer-groups")
    assert listed.status_code == 200
    assert listed.json()[0]["members"][1]["inclusion_reason"] == "Accelerator peer"
