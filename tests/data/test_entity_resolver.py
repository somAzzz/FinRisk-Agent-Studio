"""Tests for the lightweight entity resolver."""

from __future__ import annotations

from src.data.entity_resolver import normalize_name, resolve_entity
from src.schemas.entities import Entity


def _entity(
    name: str = "Acme Co.",
    ticker: str | None = None,
    cik: str | None = None,
    normalized_name: str | None = None,
    aliases: list[str] | None = None,
) -> Entity:
    return Entity(
        entity_id="ent_existing",
        name=name,
        normalized_name=normalized_name if normalized_name is not None else name.lower(),
        ticker=ticker,
        cik=cik,
        aliases=aliases or [],
        entity_type="company",
        confidence=1.0,
    )


def test_normalize_name_lowercases_and_strips() -> None:
    assert normalize_name("  Acme Corporation  ") == "acme"


def test_normalize_name_removes_inc() -> None:
    assert normalize_name("Acme, Inc.") == "acme"


def test_normalize_name_removes_corp() -> None:
    assert normalize_name("Acme Corp.") == "acme"


def test_normalize_name_removes_ltd() -> None:
    assert normalize_name("Acme Ltd.") == "acme"


def test_normalize_name_removes_llc() -> None:
    assert normalize_name("Acme LLC") == "acme"


def test_normalize_name_removes_co() -> None:
    assert normalize_name("Acme Co.") == "acme"


def test_resolve_entity_creates_new_with_stable_id() -> None:
    entity = resolve_entity("Acme Inc.", ticker="ACME", cik="0001")
    assert entity.name == "Acme Inc."
    assert entity.ticker == "ACME"
    assert entity.cik == "0001"
    assert entity.normalized_name == "acme"
    assert entity.entity_type == "company"
    assert entity.confidence == 1.0
    assert entity.entity_id.startswith("ent_")

    again = resolve_entity("Acme Inc.", ticker="ACME", cik="0001")
    assert again.entity_id == entity.entity_id


def test_resolve_entity_merges_aliases_on_normalized_name_match() -> None:
    existing = _entity(name="Acme", normalized_name="acme")
    merged = resolve_entity("Acme Co.", existing=[existing])
    assert merged.entity_id == existing.entity_id
    assert "Acme Co." in merged.aliases


def test_resolve_entity_prefers_ticker_match() -> None:
    by_name = _entity(
        name="Other Co.",
        normalized_name="other co.",
        ticker="OTH",
    )
    by_ticker = _entity(
        name="Acme Inc.",
        normalized_name="acme",
        ticker="ACME",
    )
    chosen = resolve_entity(
        "Acme Co.",
        ticker="ACME",
        existing=[by_name, by_ticker],
    )
    assert chosen.entity_id == by_ticker.entity_id


def test_resolve_entity_prefers_cik_match_over_name() -> None:
    by_name = _entity(name="Other Co.", normalized_name="other co.", cik="0002")
    by_cik = _entity(name="Acme Inc.", normalized_name="acme", cik="0001")
    chosen = resolve_entity(
        "Acme Co.",
        cik="0001",
        existing=[by_name, by_cik],
    )
    assert chosen.entity_id == by_cik.entity_id


def test_resolve_entity_creates_new_when_no_match() -> None:
    existing = _entity(name="Other Co.", normalized_name="other co.")
    fresh = resolve_entity("Brand New Inc.", existing=[existing])
    assert fresh.entity_id != existing.entity_id
    assert fresh.normalized_name == "brand new"
