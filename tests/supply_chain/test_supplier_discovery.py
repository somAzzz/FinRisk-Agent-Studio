"""v18 tests for the search-extraction + supplier-discovery layer.

The tests use a stub search provider so the v18 unit tests run
offline. Spec 03's real-mode LLM + browser adapters are out of
scope for the v18 first demo and live in follow-up specs.
"""

from __future__ import annotations

import pytest

from src.supply_chain.prompts import (
    INTENT_QUERY_TEMPLATES,
    render_query,
)


def test_intent_templates_have_required_keys() -> None:
    expected = {
        "product_supply_chain",
        "supplier_discovery",
        "component_supplier",
        "cloud_dependency",
        "datacenter_power",
        "semiconductor_supply_chain",
    }
    assert expected.issubset(INTENT_QUERY_TEMPLATES.keys())


def test_render_query_substitutes_q() -> None:
    out = render_query("product_supply_chain", "OpenAI ChatGPT")
    assert "OpenAI ChatGPT" in out
    assert "suppliers" in out


def test_render_query_unknown_intent_returns_raw_query() -> None:
    assert render_query("mystery", "Foo") == "Foo"


def test_search_results_with_no_url_are_not_confirmed() -> None:
    """A snippet with no URL is treated as a hypothesis edge."""
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "",
        "title": "Anonymous blog post",
        "snippet": "NVIDIA H100 powers AI workloads.",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["confidence"] <= 0.5
    assert evidence["is_confirmed"] is False


def test_search_results_with_no_quote_are_not_confirmed() -> None:
    """A snippet with no quote / summary is a hypothesis."""
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "https://www.reuters.com/example",
        "title": "Reuters example",
        "snippet": "",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["is_confirmed"] is False


def test_search_results_with_url_and_quote_are_confirmed() -> None:
    from src.supply_chain.evidence import build_evidence_from_search

    snippet = {
        "url": "https://www.reuters.com/example",
        "title": "Reuters example",
        "snippet": "NVIDIA H100 powers AI workloads.",
    }
    evidence = build_evidence_from_search(snippet, query="q")
    assert evidence["is_confirmed"] is True
    assert evidence["confidence"] >= 0.5
