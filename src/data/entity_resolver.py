"""Lightweight entity resolution for the extraction pipeline.

This module provides a small set of helpers that normalize and dedupe
company-like entities produced by the LLM extraction agents. The goal is
not full disambiguation, but enough to keep downstream graph storage
consistent for the first iteration of the project.
"""

from __future__ import annotations

import re

from src.schemas.entities import Entity
from src.schemas.ids import stable_id

_SUFFIXES = (
    "inc.",
    "inc",
    "corp.",
    "corp",
    "ltd.",
    "ltd",
    "corporation",
    "co.",
    "co",
    "llc",
)

_SUFFIX_PATTERN = re.compile(
    r"[,\s]+(?:" + "|".join(re.escape(s) for s in _SUFFIXES) + r")$",
    flags=re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Return a normalized version of a company name.

    The normalization is intentionally conservative: lowercase, strip
    surrounding whitespace, and remove common corporate suffixes such as
    ``Inc.``, ``Corp.``, ``Ltd.``, ``Corporation``, ``Co.``, and ``LLC``.
    """
    cleaned = (name or "").strip().lower()
    cleaned = _SUFFIX_PATTERN.sub("", cleaned)
    return cleaned.strip()


def _entity_id_for(
    name: str,
    ticker: str | None,
    cik: str | None,
) -> str:
    """Build a stable entity id from the most identifying field available."""
    key = ticker or cik or normalize_name(name)
    return stable_id("ent", key)


def _match(existing: Entity, ticker: str | None, cik: str | None, norm: str) -> bool:
    """Return True if an existing entity matches the resolution inputs."""
    if ticker and existing.ticker and existing.ticker.upper() == ticker.upper():
        return True
    if cik and existing.cik and existing.cik == cik:
        return True
    if norm and existing.normalized_name == norm:
        return True
    return False


def resolve_entity(
    name: str,
    ticker: str | None = None,
    cik: str | None = None,
    existing: list[Entity] | None = None,
) -> Entity:
    """Return an entity that represents the resolved company.

    If a matching entity already exists in ``existing`` (matched on ticker,
    CIK, or normalized name), the existing entity is copied, with the new
    name added to ``aliases`` and the ticker/CIK filled in if previously
    missing. Otherwise a brand-new entity is created with a stable id and
    default confidence ``1.0``.
    """
    norm = normalize_name(name)

    if existing:
        for entity in existing:
            if _match(entity, ticker, cik, norm):
                updated = entity.model_copy(deep=True)
                if name and name not in updated.aliases and name != updated.name:
                    updated.aliases = [*updated.aliases, name]
                if ticker and not updated.ticker:
                    updated.ticker = ticker
                if cik and not updated.cik:
                    updated.cik = cik
                if not updated.normalized_name and norm:
                    updated.normalized_name = norm
                return updated

    return Entity(
        entity_id=_entity_id_for(name, ticker, cik),
        name=name,
        normalized_name=norm,
        ticker=ticker,
        cik=cik,
        aliases=[],
        entity_type="company",
        confidence=1.0,
    )
