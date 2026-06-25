"""Rule-based supply chain claim extractor.

A minimal, deterministic extractor that scans evidence text for
supply-chain vocabulary and emits ``Claim`` records of type
``supply_chain``. Used as a fallback when no LLM client is available
so the offline MVP demo still produces populated Supply Chain sections.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from src.schemas.claims import Claim
from src.schemas.evidence import Evidence

_SUPPLY_KEYWORDS: tuple[str, ...] = (
    "supplier",
    "supplier base",
    "supply chain",
    "component sourcing",
    "sourcing",
    "shipping disruption",
    "shipping disruptions",
    "input cost",
    "input costs",
    "localiz",  # localize / localization / localized
    "reshor",
    "vendor",
    "logistics",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on punctuation and newlines."""
    raw = _SENTENCE_SPLIT_RE.split(text or "")
    return [s.strip() for s in raw if s and s.strip()]


def _sentence_has_supply_signal(sentence: str) -> bool:
    """Return True if ``sentence`` contains any supply-chain keyword."""
    lowered = sentence.lower()
    return any(kw in lowered for kw in _SUPPLY_KEYWORDS)


def extract_supply_chain_claims(evidence: list[Evidence]) -> list[Claim]:
    """Walk ``evidence`` and emit a :class:`Claim` per matching sentence.

    The output keeps ``confidence`` low (default 0.55) because this is a
    keyword-based extractor; downstream ``CriticAgent`` may tighten or
    drop claims based on evidence quality.
    """
    claims: list[Claim] = []
    seen_signatures: set[tuple[str, str]] = set()
    counter = 0
    for ev in evidence:
        for sentence in _split_sentences(ev.quote):
            if not _sentence_has_supply_signal(sentence):
                continue
            signature = (ev.evidence_id, sentence[:80])
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            counter += 1
            # Build an evidence record whose quote is the sentence itself so
            # downstream consumers (graph writer, report agent) see the
            # tight snippet that triggered the claim.
            sentence_evidence = Evidence(
                evidence_id=f"{ev.evidence_id}:sc{counter}",
                source_type=ev.source_type,
                source_id=ev.source_id,
                title=ev.title,
                url=ev.url,
                section=ev.section,
                speaker=ev.speaker,
                quote=sentence,
                retrieved_at=datetime.now(UTC),
                published_at=ev.published_at,
                char_start=ev.char_start,
                char_end=ev.char_end,
                confidence=ev.confidence,
                metadata={**ev.metadata, "extracted_via": "rule_supply_chain"},
            )
            claims.append(
                Claim(
                    claim_id=f"sc-{counter:03d}",
                    claim_type="supply_chain",
                    statement=sentence,
                    entities=[],
                    relations=[],
                    evidence=[sentence_evidence],
                    confidence=0.55,
                    counter_evidence=[],
                    metadata={"parent_evidence_id": ev.evidence_id},
                )
            )
    return claims


__all__ = ["extract_supply_chain_claims"]
