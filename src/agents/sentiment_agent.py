"""Management sentiment analysis agent.

Inspects transcript and filing MD&A evidence in an :class:`AgentState` and
emits a :class:`ManagementSentimentResult` along with corresponding
:class:`Claim` rows. This implementation uses simple heuristic rules and
performs no LLM calls, so it is deterministic and easy to test.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.analysis import (
    GuidanceSignal,
    ManagementSentimentResult,
    OverallTone,
    SentimentLabel,
    Topic,
    TopicSentiment,
)
from src.schemas.claims import Claim, ClaimType
from src.schemas.evidence import Evidence

DEFAULT_CONFIDENCE = 0.5

POSITIVE_WORDS: tuple[str, ...] = (
    "strong",
    "robust",
    "exceeded",
    "outperform",
    "record",
    "confident",
    "growth",
    "accelerat",
    "opportunity",
    "momentum",
)

NEGATIVE_WORDS: tuple[str, ...] = (
    "weak",
    "decline",
    "soft",
    "headwind",
    "challenging",
    "pressure",
    "below",
    "shortage",
    "miss",
    "uncertain",
    "cautious",
)

UNCERTAINTY_WORDS: tuple[str, ...] = (
    "uncertain",
    "volatile",
    "may",
    "could",
    "depending",
    "premature",
    "cautious",
)

DEFENSIVE_WORDS: tuple[str, ...] = (
    "as we discussed",
    "as previously",
    "we believe",
    "we think",
    "as i said",
    "as noted",
    "consistent with",
)

GUIDANCE_RAISE_WORDS: tuple[str, ...] = (
    "raise",
    "raised",
    "raise guidance",
    "increase guidance",
    "above",
    "upward",
    "narrowed",
)

GUIDANCE_LOWER_WORDS: tuple[str, ...] = (
    "lower",
    "lowered",
    "lower guidance",
    "reduce",
    "reduced",
    "below",
    "wider",
    "wide range",
)

TOPIC_KEYWORDS: dict[Topic, tuple[str, ...]] = {
    "demand": ("demand", "orders", "bookings", "end-market"),
    "margin": ("margin", "gross profit", "pricing", "cost"),
    "supply_chain": ("supply", "lead time", "shortage", "logistics"),
    "capex": ("capex", "capital expenditure", "capacity", "investment"),
    "guidance": ("guidance", "outlook", "forecast"),
    "competition": ("competitor", "competition", "market share"),
    "policy": ("policy", "regulation", "tariff", "regulatory"),
    "geopolitics": ("geopolitical", "geo-political", "sanction", "export"),
}


def _count_hits(text: str, needles: Iterable[str]) -> int:
    lowered = text.lower()
    return sum(1 for n in needles if n in lowered)


def _evidence_text(ev: Evidence) -> str:
    return ev.quote or ""


def _is_management_evidence(ev: Evidence) -> bool:
    """Management evidence originates from filings or transcripts (not web)."""
    return ev.source_type in {"transcript", "sec_filing", "sec_xbrl"}


def _is_transcript_evidence(ev: Evidence) -> bool:
    return ev.source_type == "transcript"


def _is_mda_evidence(ev: Evidence) -> bool:
    if not _is_management_evidence(ev):
        return False
    section = (ev.section or "").lower()
    if "mda" in section or "md&a" in section or "7" in section:
        return True
    return False


def _is_analyst_only(ev: Evidence) -> bool:
    """Treat transcript turns from analysts as 'analyst-only'."""
    if not _is_transcript_evidence(ev):
        return False
    role = (ev.metadata or {}).get("role")
    return role == "analyst"


def _section_label(ev: Evidence) -> str:
    if not _is_transcript_evidence(ev):
        return "mda"
    section = (ev.section or "").lower()
    if "qa" in section:
        return "qa"
    if "prepared" in section:
        return "prepared_remarks"
    return "unknown"


def _score_text(text: str) -> tuple[int, int]:
    pos = _count_hits(text, POSITIVE_WORDS)
    neg = _count_hits(text, NEGATIVE_WORDS)
    return pos, neg


def _tone_from_score(pos: int, neg: int) -> SentimentLabel:
    if pos == 0 and neg == 0:
        return "unclear"
    if pos > 0 and neg > 0:
        return "mixed"
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _overall_tone(label: SentimentLabel) -> OverallTone:
    if label == "mixed":
        return "mixed"
    if label == "positive":
        return "positive"
    if label == "negative":
        return "negative"
    return "neutral"


def _guidance_signal(text: str) -> GuidanceSignal:
    lowered = text.lower()
    if any(w in lowered for w in GUIDANCE_RAISE_WORDS):
        return "raised"
    if any(w in lowered for w in GUIDANCE_LOWER_WORDS):
        return "lowered"
    return "maintained"


def _uncertainty_score(text: str) -> float:
    hits = _count_hits(text, UNCERTAINTY_WORDS)
    if hits == 0:
        return 0.0
    return min(1.0, 0.2 + 0.15 * hits)


def _defensiveness_score(text: str) -> float:
    hits = _count_hits(text, DEFENSIVE_WORDS)
    if hits == 0:
        return 0.0
    return min(1.0, 0.2 + 0.2 * hits)


def _topic_sentiment_for(
    topic: Topic,
    keywords: tuple[str, ...],
    evidence_pool: list[Evidence],
) -> TopicSentiment | None:
    matched: list[Evidence] = []
    pos = 0
    neg = 0
    for ev in evidence_pool:
        text = _evidence_text(ev)
        if not text:
            continue
        lowered = text.lower()
        if not any(k in lowered for k in keywords):
            continue
        matched.append(ev)
        p, n = _score_text(text)
        pos += p
        neg += n
    if not matched:
        return None
    label = _tone_from_score(pos, neg)
    confidence = DEFAULT_CONFIDENCE if label != "unclear" else 0.2
    return TopicSentiment(
        topic=topic,
        sentiment=label,
        confidence=confidence,
        evidence=matched,
    )


def _claim_id(prefix: str, *parts: str) -> str:
    from src.schemas.ids import stable_id

    return stable_id(prefix, *parts)


def _build_sentiment_claim(
    ticker: str | None,
    statement: str,
    claim_type: ClaimType,
    evidence: list[Evidence],
) -> Claim:
    return Claim(
        claim_id=_claim_id("sentiment", ticker or "unknown", statement[:80]),
        claim_type=claim_type,
        statement=statement,
        evidence=evidence,
        confidence=DEFAULT_CONFIDENCE,
    )


def _summarize_evidence_by_section(
    evidence: list[Evidence],
) -> dict[str, list[Evidence]]:
    grouped: dict[str, list[Evidence]] = {
        "prepared_remarks": [],
        "qa": [],
        "mda": [],
    }
    for ev in evidence:
        if not _is_management_evidence(ev):
            continue
        if _is_analyst_only(ev):
            continue
        if _is_mda_evidence(ev):
            grouped["mda"].append(ev)
        else:
            grouped[_section_label(ev)].append(ev)
    return grouped


def _build_topic_sentiments(
    evidence_pool: list[Evidence],
) -> list[TopicSentiment]:
    sentiments: list[TopicSentiment] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        ts = _topic_sentiment_for(topic, keywords, evidence_pool)
        if ts is not None:
            sentiments.append(ts)
    return sentiments


def _compose_overall_tone(
    topic_sentiments: list[TopicSentiment],
    fallback: OverallTone,
) -> OverallTone:
    if fallback == "mixed":
        # Section-level analysis already detected divergent tones; never let
        # a sparse topic list override that signal.
        return "mixed"
    if not topic_sentiments:
        return fallback
    pos = sum(1 for t in topic_sentiments if t.sentiment == "positive")
    neg = sum(1 for t in topic_sentiments if t.sentiment == "negative")
    mixed = sum(1 for t in topic_sentiments if t.sentiment == "mixed")
    if pos and neg and (pos >= 2 or neg >= 2) and abs(pos - neg) <= 1:
        return "mixed"
    if mixed >= 2:
        return "mixed"
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return fallback


class SentimentAgent:
    """Heuristic management-sentiment analyzer.

    Splits evidence into prepared remarks, Q&A, and MD&A, scores each group
    with a small lexicon, and emits a :class:`ManagementSentimentResult`
    plus corresponding :class:`Claim` rows. Analyst-only turns are
    intentionally excluded so they cannot be misinterpreted as management
    viewpoints.
    """

    name: str = "sentiment"

    def run(self, state: AgentState) -> AgentState:
        """Analyze ``state.evidence`` and append claims/notes to ``state``."""
        evidence_pool = [
            ev
            for ev in state.evidence
            if _is_management_evidence(ev) and not _is_analyst_only(ev)
        ]

        grouped = _summarize_evidence_by_section(state.evidence)

        prepared_text = " ".join(_evidence_text(e) for e in grouped["prepared_remarks"])
        qa_text = " ".join(_evidence_text(e) for e in grouped["qa"])
        mda_text = " ".join(_evidence_text(e) for e in grouped["mda"])

        combined_text = " ".join([prepared_text, qa_text, mda_text]).strip()

        if not combined_text:
            state.notes.append("sentiment: no management evidence available")
            empty = ManagementSentimentResult(
                overall_tone="neutral",
                uncertainty=0.0,
                defensiveness=0.0,
                confidence=0.0,
                guidance_signal="unclear",
                topic_sentiment=[],
                claims=[],
            )
            return state

        prep_pos, prep_neg = _score_text(prepared_text)
        qa_pos, qa_neg = _score_text(qa_text)

        prep_label = _tone_from_score(prep_pos, prep_neg)
        qa_label = _tone_from_score(qa_pos, qa_neg)

        if prep_label == "positive" and qa_label in {"negative", "mixed"}:
            overall = "mixed"
        elif prep_label == "negative" and qa_label in {"positive", "mixed"}:
            overall = "mixed"
        elif prep_label == "mixed" or qa_label == "mixed":
            overall = "mixed"
        elif prep_label != "unclear":
            overall = _overall_tone(prep_label)
        elif qa_label != "unclear":
            overall = _overall_tone(qa_label)
        else:
            overall = "neutral"

        if qa_pos + qa_neg == 0 and prep_pos + prep_neg == 0 and mda_text:
            overall = _overall_tone(_tone_from_score(*_score_text(mda_text)))

        topic_sentiments = _build_topic_sentiments(evidence_pool)
        overall = _compose_overall_tone(topic_sentiments, overall)

        guidance_signal: GuidanceSignal
        guidance_evidence_pool = grouped["prepared_remarks"] + grouped["mda"]
        if guidance_evidence_pool:
            guidance_text = " ".join(
                _evidence_text(e) for e in guidance_evidence_pool
            )
            guidance_signal = _guidance_signal(guidance_text)
        else:
            guidance_signal = "unclear"

        uncertainty = round(_uncertainty_score(combined_text), 4)
        defensiveness = round(_defensiveness_score(combined_text), 4)

        claims: list[Claim] = []

        if grouped["prepared_remarks"]:
            claims.append(
                _build_sentiment_claim(
                    state.ticker,
                    f"Prepared remarks tone: {prep_label}.",
                    "sentiment",
                    grouped["prepared_remarks"],
                )
            )
        if grouped["qa"]:
            claims.append(
                _build_sentiment_claim(
                    state.ticker,
                    f"Q&A tone: {qa_label}.",
                    "sentiment",
                    grouped["qa"],
                )
            )
        if grouped["mda"]:
            claims.append(
                _build_sentiment_claim(
                    state.ticker,
                    f"MD&A tone: {_tone_from_score(*_score_text(mda_text))}.",
                    "sentiment",
                    grouped["mda"],
                )
            )

        if overall == "mixed":
            claims.append(
                _build_sentiment_claim(
                    state.ticker,
                    (
                        "Management tone is mixed: prepared remarks and Q&A "
                        "disagree."
                    ),
                    "sentiment",
                    grouped["prepared_remarks"] + grouped["qa"],
                )
            )

        if guidance_signal != "maintained":
            claims.append(
                _build_sentiment_claim(
                    state.ticker,
                    f"Guidance signal: {guidance_signal}.",
                    "sentiment",
                    guidance_evidence_pool,
                )
            )

        result = ManagementSentimentResult(
            overall_tone=overall,
            uncertainty=uncertainty,
            defensiveness=defensiveness,
            confidence=DEFAULT_CONFIDENCE,
            guidance_signal=guidance_signal,
            topic_sentiment=topic_sentiments,
            claims=claims,
        )

        state.claims.extend(claims)
        state.notes.append(
            f"sentiment: overall_tone={overall} "
            f"uncertainty={uncertainty:.2f} "
            f"defensiveness={defensiveness:.2f} "
            f"guidance={guidance_signal} "
            f"topics={len(topic_sentiments)}"
        )
        return state


def is_sentiment_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
