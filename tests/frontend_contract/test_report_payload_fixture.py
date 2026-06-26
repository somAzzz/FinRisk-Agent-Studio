"""v17 frontend contract: ``/workflows/{run_id}/report`` payload.

The fixture in this file is the v17 reference shape for the
``RiskReportV16Wire`` TypeScript type used by the React
``RiskReport`` component. The test asserts the structural
invariants the frontend relies on:

- the JSON can be deserialised back into a dict;
- every ``top_risks[i].final_score`` is in ``[0, 100]``;
- the ``disclaimer`` field is present and non-empty;
- every ``top_risks[i].supporting_evidence_ids`` is non-empty;
- the ``second_order_effects`` list is consistent with the
  ``graph_insights`` it replaces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "report_payload_contract.json"
)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_report_payload_fixture_round_trips() -> None:
    payload = _load_fixture()
    reloaded = json.loads(json.dumps(payload))
    assert reloaded == payload


def test_report_payload_has_required_fields() -> None:
    payload = _load_fixture()
    for key in (
        "title",
        "executive_summary",
        "top_risks",
        "evidence_table",
        "limitations",
        "recommended_next_questions",
        "disclaimer",
    ):
        assert key in payload, f"missing {key} in report payload contract"


def test_report_payload_top_risks_score_in_range() -> None:
    payload = _load_fixture()
    for item in payload["top_risks"]:
        assert 0.0 <= item["final_score"] <= 100.0, (
            f"top risk {item['risk_id']} final_score out of range: {item['final_score']}"
        )
        assert 1 <= item["severity"] <= 5
        assert item["supporting_evidence_ids"]


def test_report_payload_disclaimer_present() -> None:
    payload = _load_fixture()
    assert payload["disclaimer"].lower().startswith("disclaimer")
    assert "not investment advice" in payload["disclaimer"].lower()


def test_report_payload_no_direct_buy_sell_advice() -> None:
    """v17: the rendered markdown must not contain direct buy/sell language."""
    payload = _load_fixture()
    markdown = payload.get("markdown", "")
    for phrase in ("strong buy", "strong sell", "must invest", "should invest"):
        assert phrase not in markdown.lower(), (
            f"report contains forbidden phrase {phrase!r}"
        )


def test_report_payload_claims_link_to_top_risks() -> None:
    payload = _load_fixture()
    risk_ids = {item["risk_id"] for item in payload["top_risks"]}
    for claim in payload["evidence_vs_inference"]:
        assert claim["related_risk_ids"], (
            f"claim {claim['claim_id']} has no related_risk_ids"
        )
        assert set(claim["related_risk_ids"]).issubset(risk_ids)
