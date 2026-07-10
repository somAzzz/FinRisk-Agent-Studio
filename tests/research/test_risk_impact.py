from src.research.risk_impact import map_risk_financial_impact
from src.schemas.finrisk import ExtractedRisk


def test_maps_supply_chain_risk_without_inventing_numbers() -> None:
    risk = ExtractedRisk(
        risk_id="risk-1",
        risk_type="supply_chain",
        risk_factor="Component cost inflation and inventory disruption",
        severity=4,
        evidence_quote="Input costs may increase and disrupt production.",
        source="10-K",
        confidence=0.9,
    )

    impact = map_risk_financial_impact(
        risk,
        evidence_ids=["e-1"],
        time_horizon="6-12 months",
    )

    assert {"cost", "working_capital"} <= set(impact.drivers)
    assert {"gross_margin", "free_cash_flow"} <= set(impact.affected_metrics)
    assert impact.quantification_status == "unquantified"
    assert impact.probability is None
    assert impact.estimated_impact is None
    assert impact.confidence == 0.75
    assert impact.evidence_ids == ["e-1"]
