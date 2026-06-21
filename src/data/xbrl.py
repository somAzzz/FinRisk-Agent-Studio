"""Helpers for working with SEC XBRL company facts.

The SEC exposes a per-company JSON document at
``https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`` containing every
reported value for every ``us-gaap`` (and other taxonomy) concept. This
module provides a thin Pydantic wrapper plus a defensive extractor for a
single concept/unit combination.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class CompanyFacts(BaseModel):
    """A wrapper around the per-company XBRL facts document."""

    model_config = ConfigDict(extra="forbid")

    cik: str
    facts: dict[str, Any]


class FactValue(BaseModel):
    """A single reported XBRL fact with enough metadata to reconstruct it."""

    model_config = ConfigDict(extra="forbid")

    concept: str
    value: float
    unit: str
    period_end: date | None = None
    form_type: str | None = None
    accession_number: str | None = None


def _coerce_float(value: Any) -> float | None:
    """Best-effort conversion of an XBRL value to ``float``.

    Returns ``None`` if the value cannot be interpreted numerically.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def extract_metric(
    facts: dict[str, Any],
    concept: str,
    unit: str = "USD",
) -> list[FactValue]:
    """Return all reported values for ``concept`` in ``unit`` from XBRL facts.

    The SEC companyfacts document nests data under several taxonomies
    (``us-gaap``, ``dei``, ``ifrs-full``, ...). This helper searches every
    taxonomy present in ``facts["facts"]`` for ``concept`` and returns all
    matching rows in the requested ``unit``.

    Args:
        facts: The full ``companyfacts`` JSON document (or any subset that
            still contains the ``facts`` -> taxonomy -> concept -> ``units``
            -> unit nesting).
        concept: The XBRL concept name, e.g. ``"Revenues"`` or
            ``"NetIncomeLoss"``.
        unit: The unit key, e.g. ``"USD"`` or ``"shares"``.

    Returns:
        A list of :class:`FactValue`. Returns an empty list when the
        concept or unit is missing from the document, when the document is
        malformed, or when individual rows cannot be coerced.
    """
    if not isinstance(facts, dict):
        return []
    inner_facts = facts.get("facts")
    if not isinstance(inner_facts, dict):
        return []

    rows: list[Any] = []
    for taxonomy in inner_facts.values():
        if not isinstance(taxonomy, dict):
            continue
        concept_bucket = taxonomy.get(concept)
        if not isinstance(concept_bucket, dict):
            continue
        units = concept_bucket.get("units")
        if not isinstance(units, dict):
            continue
        candidate = units.get(unit)
        if isinstance(candidate, list):
            rows.extend(candidate)

    results: list[FactValue] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        numeric = _coerce_float(row.get("val"))
        if numeric is None:
            continue
        # Period end may be encoded as ``end`` (instant) or derived from
        # ``start``/``end`` (duration). Prefer ``end`` when present.
        period_end = _coerce_date(row.get("end"))
        results.append(
            FactValue(
                concept=concept,
                value=numeric,
                unit=unit,
                period_end=period_end,
                form_type=row.get("form") if isinstance(row.get("form"), str) else None,
                accession_number=(
                    row.get("accn")
                    if isinstance(row.get("accn"), str)
                    else None
                ),
            )
        )
    return results