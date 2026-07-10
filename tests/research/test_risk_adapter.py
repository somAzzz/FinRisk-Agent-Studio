from __future__ import annotations

from src.reports.models import RiskReportItem, RiskReportV16
from src.research.risk_adapter import risk_observations_from_report


def test_structured_report_maps_to_evidence_linked_risk_observations() -> None:
    report = RiskReportV16(
        title="ACME risk report",
        executive_summary="Summary",
        top_risks=[
            RiskReportItem(
                risk_id="supply",
                title="Supplier concentration",
                risk_type="supply_chain",
                severity=4,
                final_score=80,
                summary="One supplier remains critical.",
                supporting_evidence_ids=["filing-evidence"],
                lifecycle="emerging",
            )
        ],
        disclaimer="Research only",
    )

    observations = risk_observations_from_report(report)

    assert observations[0].risk_id == "supply"
    assert observations[0].status == "new"
    assert observations[0].evidence_ids == ["filing-evidence"]
    assert observations[0].attributes["final_score"] == 80
