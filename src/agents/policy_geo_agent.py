"""Policy and geopolitical exposure analysis agent.

Uses a simple keyword lexicon against transcript and filing evidence to
emit :class:`PolicyExposure` and :class:`GeopoliticalExposure` records,
along with corresponding :class:`Claim` rows. This implementation does
not call an LLM and is fully deterministic for testing.
"""

from __future__ import annotations

from typing import Any

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.analysis import (
    GeopoliticalExposure,
    PolicyExposure,
    PolicyExposureType,
    TimeHorizon,
)
from src.schemas.claims import Claim, ClaimType
from src.schemas.evidence import Evidence

DEFAULT_CONFIDENCE = 0.5

BENEFICIARY_HINTS: tuple[str, ...] = (
    "beneficiary",
    "benefit",
    "support",
    "incentive",
    "subsidy",
    "tailwind",
    "opportunity",
    "credit",
)

RISK_HINTS: tuple[str, ...] = (
    "risk",
    "exposure",
    "headwind",
    "negative",
    "adverse",
    "penalty",
    "shortage",
    "tariff",
    "sanction",
    "export control",
)

POLICY_RULES: dict[str, dict[str, Any]] = {
    "IRA": {
        "keywords": (
            "inflation reduction act",
            " ira ",
            "(ira)",
            "section 45x",
            "section 48e",
            "clean energy credit",
        ),
        "segments": ("clean energy", "solar", "ev", "battery", "storage"),
        "time_horizon": "long",
    },
    "CHIPS": {
        "keywords": (
            "chips act",
            "chips and science",
            "semiconductor incentive",
            "section 48d",
        ),
        "segments": ("semiconductor", "fab", "foundry", "wafer"),
        "time_horizon": "mid",
    },
    "tariffs": {
        "keywords": ("tariff", "tariffs", "import duty", "section 301"),
        "segments": ("imports", "china", "steel", "aluminum", "consumer goods"),
        "time_horizon": "short",
    },
    "export_controls": {
        "keywords": (
            "export control",
            "export restrictions",
            "entity list",
            "ear99",
            "bis restrictions",
        ),
        "segments": ("semiconductor", "ai", "telecom"),
        "time_horizon": "mid",
    },
    "carbon_regulation": {
        "keywords": (
            "carbon",
            "emissions",
            "esg",
            " cbam ",
            "carbon border",
            "climate disclosure",
        ),
        "segments": ("energy", "manufacturing", "transportation"),
        "time_horizon": "long",
    },
    "defense_spending": {
        "keywords": (
            "defense spending",
            "dod budget",
            "defense contract",
            "pentagon",
        ),
        "segments": ("defense", "aerospace", "government"),
        "time_horizon": "long",
    },
    "healthcare_regulation": {
        "keywords": (
            "fda",
            "medicare",
            "medicaid",
            "drug pricing",
            "inflation rebate",
            "340b",
        ),
        "segments": ("pharma", "biotech", "medical devices"),
        "time_horizon": "mid",
    },
    "antitrust": {
        "keywords": (
            "antitrust",
            "doj",
            "ftc",
            "monopoly",
            "competition law",
        ),
        "segments": ("big tech", "platform", "media"),
        "time_horizon": "mid",
    },
    "tax_policy": {
        "keywords": (
            "corporate tax",
            "tax reform",
            "global minimum tax",
            "oecd pillar",
            "section 174",
        ),
        "segments": ("multinational", "technology", "manufacturing"),
        "time_horizon": "mid",
    },
    "reshoring": {
        "keywords": (
            "reshoring",
            "localization",
            "friend-shoring",
            "onshore",
            "made in america",
        ),
        "segments": ("manufacturing", "supply chain", "industrial"),
        "time_horizon": "long",
    },
}

GEO_RULES: dict[str, dict[str, Any]] = {
    "sanction": {
        "keywords": (
            "sanction",
            "sanctions",
            "ofac",
            "sdn list",
            "embargo",
        ),
        "regions": ("russia", "iran", "north korea", "syria", "venezuela"),
        "base_score": 0.7,
    },
    "export_control": {
        "keywords": (
            "export control",
            "export ban",
            "entity list",
            "advanced computing",
            "semiconductor export",
        ),
        "regions": ("china", "russia", "iran"),
        "base_score": 0.65,
    },
    "conflict": {
        "keywords": (
            "war",
            "conflict",
            "invasion",
            "military",
            "taiwan strait",
            "red sea",
        ),
        "regions": ("ukraine", "middle east", "taiwan", "israel", "gaza"),
        "base_score": 0.7,
    },
    "tariff": {
        "keywords": ("tariff", "trade war", "section 301", "import duty"),
        "regions": ("china", "mexico", "europe", "eu"),
        "base_score": 0.55,
    },
    "supply_disruption": {
        "keywords": (
            "supply disruption",
            "shortage",
            "bottleneck",
            "lead time",
            "logistics",
        ),
        "regions": ("asia", "china", "global"),
        "base_score": 0.5,
    },
    "shipping_disruption": {
        "keywords": (
            "shipping",
            "freight",
            "red sea",
            "suez",
            "panama canal",
            "port congestion",
        ),
        "regions": ("red sea", "suez", "panama", "asia"),
        "base_score": 0.55,
    },
    "commodity_shock": {
        "keywords": (
            "oil price",
            "natural gas",
            "commodity",
            "lng",
            "grain",
        ),
        "regions": ("global", "middle east", "russia", "ukraine"),
        "base_score": 0.5,
    },
    "localization_requirement": {
        "keywords": (
            "localization",
            "local content",
            "data residency",
            "made in country",
        ),
        "regions": ("china", "india", "europe", "russia"),
        "base_score": 0.4,
    },
}


def _claim_id(prefix: str, *parts: str) -> str:
    from src.schemas.ids import stable_id

    return stable_id(prefix, *parts)


def _classify_policy(text_lower: str) -> PolicyExposureType:
    if any(h in text_lower for h in BENEFICIARY_HINTS):
        if any(h in text_lower for h in RISK_HINTS):
            return "mixed"
        return "beneficiary"
    if any(h in text_lower for h in RISK_HINTS):
        return "risk"
    return "unknown"


def _is_management_evidence(ev: Evidence) -> bool:
    return ev.source_type in {"transcript", "sec_filing", "sec_xbrl"}


def _is_analyst_only(ev: Evidence) -> bool:
    if ev.source_type != "transcript":
        return False
    role = (ev.metadata or {}).get("role")
    return role == "analyst"


def _eligible_evidence(state: AgentState) -> list[Evidence]:
    return [
        ev
        for ev in state.evidence
        if _is_management_evidence(ev) and not _is_analyst_only(ev)
    ]


def _matched_evidence(
    text_lower: str, evidence: list[Evidence], keywords: tuple[str, ...]
) -> list[Evidence]:
    matched: list[Evidence] = []
    for ev in evidence:
        quote_lower = (ev.quote or "").lower()
        if any(k in quote_lower for k in keywords):
            matched.append(ev)
    return matched


def _affected_segments(
    text_lower: str, default: tuple[str, ...]
) -> list[str]:
    found: list[str] = []
    for seg in default:
        if seg in text_lower:
            found.append(seg)
    return found


def _detect_policy_exposures(
    state: AgentState,
) -> list[PolicyExposure]:
    evidence = _eligible_evidence(state)
    if not evidence:
        return []

    exposures: list[PolicyExposure] = []
    for policy_name, rule in POLICY_RULES.items():
        keywords: tuple[str, ...] = rule["keywords"]
        matched = _matched_evidence(
            text_lower=" ".join((ev.quote or "").lower() for ev in evidence),
            evidence=evidence,
            keywords=keywords,
        )
        if not matched:
            continue

        combined_text = " ".join((ev.quote or "") for ev in matched)
        exposure_type = _classify_policy(combined_text.lower())
        affected = _affected_segments(
            combined_text.lower(), rule["segments"]
        )
        time_horizon: TimeHorizon = rule["time_horizon"]

        claim = Claim(
            claim_id=_claim_id("policy", state.ticker or "unknown", policy_name),
            claim_type="policy_exposure",
            statement=(
                f"{state.ticker or 'Company'} is exposed to {policy_name} "
                f"({exposure_type})."
            ),
            evidence=matched,
            confidence=DEFAULT_CONFIDENCE,
        )

        exposures.append(
            PolicyExposure(
                policy_name=policy_name,
                exposure_type=exposure_type,
                affected_segments=affected,
                time_horizon=time_horizon,
                confidence=DEFAULT_CONFIDENCE,
                evidence=matched,
                claims=[claim],
            )
        )

    return exposures


def _detect_geo_exposures(
    state: AgentState,
) -> list[GeopoliticalExposure]:
    evidence = _eligible_evidence(state)
    if not evidence:
        return []

    exposures: list[GeopoliticalExposure] = []
    for risk_type, rule in GEO_RULES.items():
        keywords: tuple[str, ...] = rule["keywords"]
        matched = _matched_evidence(
            text_lower=" ".join((ev.quote or "").lower() for ev in evidence),
            evidence=evidence,
            keywords=keywords,
        )
        if not matched:
            continue

        combined_lower = " ".join((ev.quote or "").lower() for ev in matched)
        region = _pick_region(combined_lower, rule["regions"])
        score = _score_geo(rule["base_score"], matched, region)

        exposures.append(
            GeopoliticalExposure(
                risk_type=risk_type,
                region=region,
                impacted_entities=[],
                supply_chain_paths=[],
                risk_score=score,
                opportunity_offset=[],
                evidence=matched,
            )
        )

    return exposures


def _pick_region(text_lower: str, candidates: tuple[str, ...]) -> str:
    for c in candidates:
        if c in text_lower:
            return c
    return "global"


def _score_geo(base: float, matched: list[Evidence], region: str) -> float:
    score = base
    if len(matched) >= 3:
        score += 0.1
    elif len(matched) >= 2:
        score += 0.05
    if region != "global":
        score += 0.05
    return round(min(1.0, max(0.0, score)), 4)


def _policy_claim(exposure: PolicyExposure, ticker: str | None) -> Claim:
    return Claim(
        claim_id=_claim_id(
            "policy", ticker or "unknown", exposure.policy_name
        ),
        claim_type="policy_exposure",
        statement=(
            f"{ticker or 'Company'} exposure to {exposure.policy_name} "
            f"is {exposure.exposure_type}."
        ),
        evidence=exposure.evidence,
        confidence=exposure.confidence,
    )


def _geo_claim(exposure: GeopoliticalExposure, ticker: str | None) -> Claim:
    return Claim(
        claim_id=_claim_id(
            "geo", ticker or "unknown", exposure.risk_type, exposure.region
        ),
        claim_type="geopolitical_exposure",
        statement=(
            f"{ticker or 'Company'} geopolitical exposure: "
            f"{exposure.risk_type} in {exposure.region} "
            f"(risk_score={exposure.risk_score:.2f})."
        ),
        evidence=exposure.evidence,
        confidence=DEFAULT_CONFIDENCE,
    )


class PolicyGeoAgent:
    """Keyword-based policy and geopolitical exposure analyzer.

    Scans eligible evidence (transcripts and filings, analyst turns
    excluded) for policy and geopolitical keywords, builds
    :class:`PolicyExposure` and :class:`GeopoliticalExposure` records, and
    pushes matching :class:`Claim` rows into the runtime state.
    """

    name: str = "policy_geo"

    def run(self, state: AgentState) -> AgentState:
        """Analyze ``state.evidence`` and append claims to ``state``."""
        policy_exposures = _detect_policy_exposures(state)
        geo_exposures = _detect_geo_exposures(state)

        for pe in policy_exposures:
            for claim in pe.claims:
                state.claims.append(claim)

        for ge in geo_exposures:
            state.claims.append(_geo_claim(ge, state.ticker))

        state.notes.append(
            "policy_geo: "
            f"policies={len(policy_exposures)} "
            f"geo_risks={len(geo_exposures)}"
        )
        return state


def is_policy_geo_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
