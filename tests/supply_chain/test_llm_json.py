"""LLM JSON parsing and coercion robustness tests."""

from __future__ import annotations

from src.supply_chain.llm import extract_json
from src.supply_chain.steps.requirement_decomposer import _coerce_requirements
from src.supply_chain.steps.supplier_discovery import _coerce_supplier_rows


def test_extract_json_rejects_truncated_top_level_object() -> None:
    content = '{"suppliers":[{"supplier_name":"TSMC"}'

    assert extract_json(content) is None


def test_extract_json_accepts_prefixed_complete_json() -> None:
    content = 'Result: {"ok": true, "items": ["TSMC"]}'

    assert extract_json(content) == {"ok": True, "items": ["TSMC"]}


def test_coerce_requirements_accepts_common_alias_keys() -> None:
    rows = _coerce_requirements(
        {
            "product_requirements": [
                {
                    "name": "Advanced packaging",
                    "node_type": "infrastructure",
                    "importance": 0.8,
                    "confidence": 0.7,
                }
            ]
        }
    )

    assert rows[0]["label"] == "Advanced packaging"
    assert rows[0]["node_type"] == "infrastructure"


def test_coerce_supplier_rows_accepts_single_candidate_dict() -> None:
    rows = _coerce_supplier_rows(
        {
            "requirement": "HBM memory",
            "company": "SK hynix",
            "ticker": None,
            "product_or_service": "HBM3",
            "confidence": 0.86,
        }
    )

    assert rows[0]["supplier_name"] == "SK hynix"
    assert rows[0]["requirement_label"] == "HBM memory"
