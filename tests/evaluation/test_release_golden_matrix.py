from __future__ import annotations

import json
from pathlib import Path


def test_release_golden_matrix_has_30_unique_evidence_safe_cases() -> None:
    path = Path(__file__).resolve().parents[2] / "eval" / "golden_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert len(cases) >= 30
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert all(case["must_have_evidence"] for case in cases)
    assert all(case["analysis_goal"].strip() for case in cases)
    assert all(case["should_not_contain"] for case in cases)
    categories = {case.get("category", "legacy") for case in cases}
    assert {
        "bank",
        "biotech",
        "energy",
        "foreign_issuer",
        "no_change",
        "provider_missing",
        "restatement",
        "saas",
        "semiconductor",
        "source_conflict",
    } <= categories
