"""Tests for :mod:`src.data.xbrl`."""

from __future__ import annotations

import json

from src.data.xbrl import CompanyFacts, FactValue, extract_metric


def _make_revenue_facts() -> dict:
    """Return a minimal ``companyfacts``-shaped payload for Revenue (USD)."""
    return {
        "cik": "0000320193",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            {
                                "end": "2021-09-25",
                                "val": 365817000000,
                                "accn": "0000320193-21-000105",
                                "form": "10-K",
                                "filed": "2021-10-29",
                            },
                            {
                                "end": "2020-09-26",
                                "val": 274515000000,
                                "accn": "0000320193-20-000096",
                                "form": "10-K",
                                "filed": "2020-10-30",
                            },
                        ]
                    },
                }
            }
        },
    }


def test_extract_metric_returns_facts_for_known_concept() -> None:
    """``extract_metric`` should parse a known us-gaap concept correctly."""
    facts = _make_revenue_facts()
    values = extract_metric(facts, concept="Revenues", unit="USD")
    assert len(values) == 2
    assert all(isinstance(v, FactValue) for v in values)
    assert values[0].concept == "Revenues"
    assert values[0].unit == "USD"
    assert values[0].value == 365817000000
    assert values[0].period_end is not None
    assert values[0].period_end.isoformat() == "2021-09-25"
    assert values[0].form_type == "10-K"
    assert values[0].accession_number == "0000320193-21-000105"
    assert values[1].value == 274515000000


def test_extract_metric_returns_empty_for_missing_concept() -> None:
    """Missing concepts should yield an empty list, not an exception."""
    facts = _make_revenue_facts()
    assert extract_metric(facts, concept="NotAConcept", unit="USD") == []


def test_extract_metric_returns_empty_for_missing_unit() -> None:
    """Missing unit keys should yield an empty list."""
    facts = _make_revenue_facts()
    assert extract_metric(facts, concept="Revenues", unit="EUR") == []


def test_extract_metric_returns_empty_for_empty_document() -> None:
    """Empty / malformed inputs should yield an empty list, never crash."""
    assert extract_metric({}, concept="Revenues") == []
    assert extract_metric({"facts": {}}, concept="Revenues") == []
    assert extract_metric(
        {"facts": {"us-gaap": {}}}, concept="Revenues"
    ) == []


def test_extract_metric_skips_rows_with_invalid_values() -> None:
    """Rows whose ``val`` is not numeric are skipped, not crash-inducing."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2021-09-25", "val": "not-a-number"},
                            {"end": "2020-09-26", "val": 1000},
                        ]
                    }
                }
            }
        }
    }
    values = extract_metric(facts, "Revenues", "USD")
    assert len(values) == 1
    assert values[0].value == 1000


def test_extract_metric_accepts_string_numbers() -> None:
    """The SEC occasionally emits numeric strings; ``extract_metric`` handles them."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2021-09-25", "val": "12345"},
                        ]
                    }
                }
            }
        }
    }
    values = extract_metric(facts, "Revenues", "USD")
    assert values[0].value == 12345


def test_extract_metric_ignores_non_dict_top_level() -> None:
    """``extract_metric`` returns ``[]`` for non-dict inputs."""
    assert extract_metric([], concept="Revenues") == []  # type: ignore[arg-type]
    assert extract_metric("not a dict", concept="Revenues") == []  # type: ignore[arg-type]


def test_extract_metric_period_end_optional() -> None:
    """If ``end`` is missing or invalid, ``period_end`` is ``None``."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [{"val": 1000, "accn": "X"}]}
                }
            }
        }
    }
    values = extract_metric(facts, "Revenues", "USD")
    assert values[0].period_end is None
    assert values[0].accession_number == "X"


def test_company_facts_round_trips_through_json() -> None:
    """A :class:`CompanyFacts` instance should serialize via ``model_dump_json``."""
    company = CompanyFacts(cik="0000320193", facts={"us-gaap": {"label": "x"}})
    blob = company.model_dump_json()
    parsed = json.loads(blob)
    assert parsed["cik"] == "0000320193"
    assert parsed["facts"] == {"us-gaap": {"label": "x"}}
    # Round-trip back into a model.
    again = CompanyFacts.model_validate_json(blob)
    assert again == company


def test_fact_value_round_trips_through_json() -> None:
    """A :class:`FactValue` should survive JSON serialization."""
    from datetime import date

    fact = FactValue(
        concept="Revenues",
        value=100.5,
        unit="USD",
        period_end=date(2024, 1, 1),
        form_type="10-K",
        accession_number="0001",
    )
    blob = fact.model_dump_json()
    again = FactValue.model_validate_json(blob)
    assert again == fact


def test_company_facts_forbids_extra_fields() -> None:
    """``CompanyFacts`` uses ``extra='forbid'`` so unknown fields raise."""
    import pytest

    with pytest.raises(Exception):
        CompanyFacts(cik="1", facts={}, unknown_field=True)  # type: ignore[call-arg]


def test_fact_value_forbids_extra_fields() -> None:
    """``FactValue`` uses ``extra='forbid'`` so unknown fields raise."""
    import pytest

    with pytest.raises(Exception):
        FactValue(concept="X", value=1.0, unit="USD", bogus="y")  # type: ignore[call-arg]