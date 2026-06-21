"""Risk assessment agent.

Aggregates risk claims already present in :class:`AgentState`, categorizes
each by a small keyword lexicon, and emits a :class:`RiskAssessment` with
an overall risk score and a sorted list of top risk categories. No LLM is
used: classification is deterministic and confidence defaults to 0.5.
"""

from __future__ import annotations

from typing import Any

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.analysis import RiskAssessment
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence

DEFAULT_CONFIDENCE = 0.5

RISK_CATEGORIES: tuple[str, ...] = (
    "macro",
    "policy",
    "geopolitical",
    "supply_chain",
    "customer_concentration",
    "margin",
    "legal",
    "market",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "macro": (
        "macro",
        "recession",
        "inflation",
        "interest rate",
        "consumer",
        "cpi",
        "fomc",
    ),
    "policy": (
        "policy",
        "regulation",
        "regulatory",
        "tariff",
        "ira",
        "chips",
        "export control",
        "fda",
    ),
    "geopolitical": (
        "geopolitical",
        "geopolitics",
        "sanction",
        "war",
        "conflict",
        "taiwan",
        "russia",
        "china",
    ),
    "supply_chain": (
        "supply chain",
        "supplier",
        "logistics",
        "shortage",
        "lead time",
        "bottleneck",
    ),
    "customer_concentration": (
        "customer concentration",
        "top customer",
        "key customer",
        "single customer",
        "concentration",
    ),
    "margin": (
        "margin",
        "gross profit",
        "pricing pressure",
        "input cost",
        "cost inflation",
    ),
    "legal": (
        "legal",
        "lawsuit",
        "litigation",
        "antitrust",
        "investigation",
        "sec investigation",
        "subpoena",
    ),
    "market": (
        "market share",
        "competition",
        "competitor",
        "demand",
        "pricing",
        "demand weakness",
    ),
}


def _text_of_claim(claim: Claim) -> str:
    parts: list[str] = [claim.statement or ""]
    for ev in claim.evidence:
        if ev.quote:
            parts.append(ev.quote)
    return " ".join(parts).lower()


def _categorize(claim: Claim) -> list[str]:
    text = _text_of_claim(claim)
    matches: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            matches.append(category)
    return matches


def _company_entity(state: AgentState) -> Entity:
    for ent in state.entities:
        if ent.entity_type == "company":
            return ent
    name = state.company_name or state.ticker or "Unknown"
    normalized = name.lower().replace(" ", "_")
    return Entity(
        entity_id=f"company:{normalized}",
        name=name,
        entity_type="company",
        normalized_name=normalized,
        ticker=state.ticker,
        aliases=[],
        confidence=1.0,
    )


def _risk_claims(state: AgentState) -> list[Claim]:
    return [c for c in state.claims if c.claim_type == "risk"]


def _score_for_categories(categories: list[str]) -> float:
    if not categories:
        return DEFAULT_CONFIDENCE
    return round(min(1.0, 0.4 + 0.1 * len(categories)), 4)


def _overall_risk_score(
    risk_claims: list[Claim],
    category_counts: dict[str, int],
) -> float:
    if not risk_claims:
        return 0.0
    claim_count = len(risk_claims)
    category_diversity = min(len(category_counts), 4) / 4.0
    confidence_avg = sum(c.confidence for c in risk_claims) / claim_count
    base = 0.3 * (claim_count / max(1.0, claim_count + 4.0))
    score = 0.4 * category_diversity + 0.3 * base + 0.3 * confidence_avg
    return round(min(1.0, max(0.0, score)), 4)


def _top_categories(
    category_counts: dict[str, int],
    max_items: int = 5,
) -> list[str]:
    ordered = sorted(
        category_counts.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return [name for name, _count in ordered[:max_items] if _count > 0]


def _build_evidence_pool(state: AgentState, risk_claims: list[Claim]) -> list[Evidence]:
    seen: set[str] = set()
    pool: list[Evidence] = []
    for claim in risk_claims:
        for ev in claim.evidence:
            if ev.evidence_id in seen:
                continue
            seen.add(ev.evidence_id)
            pool.append(ev)
    for ev in state.evidence:
        if ev.evidence_id in seen:
            continue
        seen.add(ev.evidence_id)
        pool.append(ev)
    return pool


def _category_summary_claim(
    ticker: str | None,
    category: str,
    count: int,
) -> Claim:
    return Claim(
        claim_id=f"risk_category:{ticker or 'unknown'}:{category}",
        claim_type="risk",
        statement=(
            f"{count} risk claim(s) classified under '{category}' category."
        ),
        evidence=[],
        confidence=DEFAULT_CONFIDENCE,
        metadata={"category": category, "count": count},
    )


def _coerce_metadata(claim: Claim) -> dict[str, Any]:
    md = dict(claim.metadata or {})
    return md


class RiskAgent:
    """Keyword-based risk aggregator and categorizer.

    Walks ``state.claims``, keeps ``claim_type == "risk"`` rows, assigns
    each to one or more :data:`RISK_CATEGORIES` via keyword matching,
    computes an overall risk score, and emits a :class:`RiskAssessment`
    plus per-category summary claims back into the state.
    """

    name: str = "risk"

    def run(self, state: AgentState) -> AgentState:
        """Analyze ``state.claims`` and append a :class:`RiskAssessment`."""
        risk_claims = _risk_claims(state)
        category_counts: dict[str, int] = {cat: 0 for cat in RISK_CATEGORIES}
        per_claim_categories: list[tuple[Claim, list[str]]] = []

        for claim in risk_claims:
            categories = _categorize(claim)
            per_claim_categories.append((claim, categories))
            for cat in categories:
                category_counts[cat] += 1

        if not risk_claims:
            state.notes.append("risk: no risk claims found in state")

        top_categories = _top_categories(category_counts)
        overall_score = _overall_risk_score(risk_claims, category_counts)
        company = _company_entity(state)
        evidence_pool = _build_evidence_pool(state, risk_claims)

        for claim, categories in per_claim_categories:
            if not categories:
                continue
            metadata = _coerce_metadata(claim)
            metadata.setdefault("categories", categories)
            claim.metadata = metadata

        summary_claims: list[Claim] = []
        for category, count in category_counts.items():
            if count > 0:
                summary_claims.append(
                    _category_summary_claim(state.ticker, category, count)
                )

        result = RiskAssessment(
            company=company,
            risks=risk_claims,
            overall_risk_score=overall_score,
            top_risk_categories=top_categories,
            evidence=evidence_pool,
            metadata={
                "category_counts": category_counts,
                "ticker": state.ticker,
            },
        )

        state.claims.extend(summary_claims)
        state.entities.append(company)
        state.notes.append(
            "risk: "
            f"claims={len(risk_claims)} "
            f"score={overall_score:.2f} "
            f"top={top_categories}"
        )
        return state


def is_risk_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
