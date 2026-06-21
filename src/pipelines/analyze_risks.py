"""End-to-end risk analysis pipeline.

Builds a fresh :class:`AgentState` from filing, transcript, and web
evidence, then runs :class:`RiskAgent` to produce a
:class:`RiskAssessment` for the requested ticker.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.risk_agent import CATEGORY_KEYWORDS, RiskAgent
from src.agents.state import AgentState
from src.schemas.analysis import RiskAssessment
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.filings import FilingRecord
from src.schemas.ids import stable_id
from src.schemas.transcripts import Transcript

RISK_CATEGORY_ORDER: tuple[str, ...] = (
    "macro",
    "policy",
    "geopolitical",
    "supply_chain",
    "customer_concentration",
    "margin",
    "legal",
    "market",
)


def _filing_evidence(
    filings: list[FilingRecord], ticker: str
) -> list[Evidence]:
    """Convert filing sections into :class:`Evidence` rows."""
    now = datetime.now(tz=timezone.utc)
    evidence: list[Evidence] = []
    for filing in filings:
        source_id = (
            filing.accession_number
            or f"{filing.cik}-{filing.form_type}-{filing.year or 0}"
        )
        for index, (section_name, text) in enumerate(filing.sections.items()):
            if not text:
                continue
            evidence.append(
                Evidence(
                    evidence_id=f"{source_id}:{section_name}:{index}",
                    source_type="sec_filing",
                    source_id=source_id,
                    title=filing.company_name or filing.cik,
                    url=filing.url,
                    section=section_name,
                    quote=text,
                    retrieved_at=now,
                    confidence=0.8,
                    metadata={
                        "cik": filing.cik,
                        "ticker": filing.ticker or ticker,
                        "form_type": filing.form_type,
                        "year": filing.year,
                    },
                )
            )
    return evidence


def _transcript_evidence(
    transcripts: list[Transcript], ticker: str
) -> list[Evidence]:
    """Convert each transcript turn into an :class:`Evidence` row."""
    now = datetime.now(tz=timezone.utc)
    evidence: list[Evidence] = []
    for transcript in transcripts:
        for turn in transcript.turns:
            if not turn.text or not turn.text.strip():
                continue
            evidence.append(
                Evidence(
                    evidence_id=(
                        f"{transcript.transcript_id}:turn:{turn.turn_index}"
                    ),
                    source_type="transcript",
                    source_id=transcript.transcript_id,
                    title=transcript.title
                    or f"{transcript.ticker} Q{transcript.quarter}",
                    url=transcript.url,
                    section=turn.section,
                    speaker=turn.speaker,
                    quote=turn.text,
                    retrieved_at=now,
                    published_at=transcript.published_at,
                    confidence=0.8,
                    metadata={
                        "ticker": transcript.ticker or ticker,
                        "year": transcript.year,
                        "quarter": transcript.quarter,
                        "role": turn.role,
                        "turn_index": turn.turn_index,
                    },
                )
            )
    return evidence


def _company_name_from_filings(
    filings: list[FilingRecord], ticker: str
) -> str:
    for filing in filings:
        if filing.company_name:
            return filing.company_name
    return ticker


def _categories_in(quote: str) -> list[str]:
    lowered = (quote or "").lower()
    return [
        cat
        for cat, kws in CATEGORY_KEYWORDS.items()
        if any(k in lowered for k in kws)
    ]


def _seed_risk_claims(state: AgentState) -> None:
    """Add lightweight risk claims so the agent has something to categorize."""
    for ev in state.evidence:
        if ev.source_type not in {"transcript", "sec_filing", "web", "browser"}:
            continue
        categories = _categories_in(ev.quote or "")
        if not categories:
            continue
        claim = Claim(
            claim_id=stable_id(
                "risk_seed", ev.evidence_id, ",".join(categories)
            ),
            claim_type="risk",
            statement="Risk signal detected: " + ", ".join(categories) + ".",
            evidence=[ev],
            confidence=0.5,
            metadata={"categories": categories},
        )
        state.claims.append(claim)


def _build_assessment(state: AgentState) -> RiskAssessment:
    risk_claims = [c for c in state.claims if c.claim_type == "risk"]
    category_counts: dict[str, int] = {cat: 0 for cat in RISK_CATEGORY_ORDER}
    for claim in risk_claims:
        for cat in claim.metadata.get("categories", []):
            if cat in category_counts:
                category_counts[cat] += 1

    top = sorted(
        ((name, count) for name, count in category_counts.items() if count > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )
    top_names = [name for name, _count in top][:5]

    if risk_claims:
        diversity = min(len(top_names), 4) / 4.0
        confidence_avg = sum(c.confidence for c in risk_claims) / len(risk_claims)
        base = 0.3 * (len(risk_claims) / max(1.0, len(risk_claims) + 4.0))
        overall = round(
            min(
                1.0,
                max(0.0, 0.4 * diversity + 0.3 * base + 0.3 * confidence_avg),
            ),
            4,
        )
    else:
        overall = 0.0

    ticker = state.ticker or "UNKNOWN"
    company_name = state.company_name or ticker
    company = Entity(
        entity_id=f"company:{ticker.lower()}",
        name=company_name,
        entity_type="company",
        normalized_name=ticker.lower(),
        ticker=ticker,
        confidence=1.0,
    )

    return RiskAssessment(
        company=company,
        risks=risk_claims,
        overall_risk_score=overall,
        top_risk_categories=top_names,
        evidence=list(state.evidence),
        metadata={
            "category_counts": category_counts,
            "ticker": ticker,
        },
    )


def analyze_company_risks(
    ticker: str,
    filings: list[FilingRecord],
    transcripts: list[Transcript],
    web_evidence: list[Evidence],
) -> RiskAssessment:
    """Build a :class:`RiskAssessment` for ``ticker`` from raw evidence.

    The pipeline:

    1. Converts filings and transcripts into :class:`Evidence` rows.
    2. Augments with the supplied ``web_evidence``.
    3. Seeds risk claims by keyword matching.
    4. Runs :class:`RiskAgent` to ensure the state is well-formed.
    5. Returns a :class:`RiskAssessment` built from the populated state.
    """
    company_name = _company_name_from_filings(filings, ticker)
    state = AgentState(
        goal=f"analyze risks for {ticker}",
        ticker=ticker,
        company_name=company_name,
    )

    state.evidence.extend(_filing_evidence(filings, ticker))
    state.evidence.extend(_transcript_evidence(transcripts, ticker))
    state.evidence.extend(web_evidence)

    _seed_risk_claims(state)

    agent = RiskAgent()
    agent.run(state)

    return _build_assessment(state)
