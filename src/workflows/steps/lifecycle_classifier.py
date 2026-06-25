"""Step 5b: classify each filing risk's lifecycle.

Sits between :class:`RiskScorerStep` and :class:`GraphReasonerStep`.
For every ``ExtractedRisk`` the classifier emits one
:class:`RiskLifecycleAnnotation` (``current`` / ``emerging`` / ``receding``
/ ``unknown``) plus a confidence score, reasoning, and a list of
``evidence_id``s that drove the classification.

The classification is deterministic — no LLM call — so it is fast,
cheap, and reproducible. Three rules, in order:

1. **current** — a recent web evidence row (<30 days old) supports the
   risk and shares a quote fragment with the filing's
   ``evidence_quote``. This is the "market is currently worried about
   this same risk" case.
2. **receding** — no recent web evidence AND the available web evidence
   contradicts the risk. The market is moving past it.
3. **emerging** — web evidence exists with the same risk_factor keyword
   but the filing has no evidence_quote for it (so it has not been
   materialised in the 10-K yet). The market is seeing it first.
4. **unknown** — fallback when no rule matches.

The frontend ``LifecycleBadge`` component reads these annotations to
render a green / amber / gray dot next to each top-risk.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from src.schemas.finrisk import RiskLifecycleAnnotation
from src.workflows.state import FinRiskWorkflowState
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

# Risks whose ``evidence_quote`` contains any of these substrings are
# treated as "market-supported" for the current-lifecycle check.
_RECENT_WEB_WINDOW = timedelta(days=30)

# Substring matches inside web-evidence quotes that flip a risk to
# "receding". Conservative — we only treat risk as receding when the
# market is explicitly contradicting the filing.
_CONTRADICTION_HINTS = (
    "no longer",
    "no longer material",
    "have largely subsided",
    "abated",
    "have decreased",
    "moderated",
    "no longer expected",
    "is no longer a material",
)


class LifecycleClassifierStep(WorkflowStep):
    """Classify each filing risk as current / emerging / receding / unknown."""

    name = "lifecycle_classifier"
    critical = False

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        annotations: list[RiskLifecycleAnnotation] = []
        now = datetime.now(tz=UTC)
        web_evidence = [
            e for e in state.normalized_evidence if e.source_type == "web"
        ]
        recent_web = [
            e
            for e in web_evidence
            if _is_recent(e.published_at, now, RECENT_WEB_WINDOW)
        ]
        contradicting_web = [
            e
            for e in web_evidence
            if any(hint in e.quote.lower() for hint in _CONTRADICTION_HINTS)
        ]

        for risk in state.filing_risks:
            annotation = _classify_one(
                risk,
                web_evidence=web_evidence,
                recent_web=recent_web,
                contradicting_web=contradicting_web,
                now=now,
            )
            annotations.append(annotation)

        state.risk_lifecycles = annotations
        logger.info(
            "LifecycleClassifier: %d current / %d emerging / %d receding / %d unknown",
            sum(1 for a in annotations if a.lifecycle == "current"),
            sum(1 for a in annotations if a.lifecycle == "emerging"),
            sum(1 for a in annotations if a.lifecycle == "receding"),
            sum(1 for a in annotations if a.lifecycle == "unknown"),
        )
        return state


def _is_recent(
    published_at: datetime | None, now: datetime, window: timedelta
) -> bool:
    if published_at is None:
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    return (now - published_at) <= window


def _classify_one(
    risk: Any,
    *,
    web_evidence: list[Any],
    recent_web: list[Any],
    contradicting_web: list[Any],
    now: datetime,
) -> RiskLifecycleAnnotation:
    """Apply the rules in order. First match wins."""
    risk_factor = getattr(risk, "risk_factor", "") or ""
    quote = getattr(risk, "evidence_quote", "") or ""

    # Rule 1: current = recent web supports the risk with a quote overlap.
    if recent_web and quote:
        supporting = [
            e
            for e in recent_web
            if _quote_overlaps(quote, e.quote)
            or _factor_overlaps(risk_factor, e.quote)
        ]
        if supporting:
            return RiskLifecycleAnnotation(
                risk_id=risk.risk_id,
                lifecycle="current",
                confidence=0.85,
                reasoning=(
                    f"{len(supporting)} recent web evidence row(s) within "
                    f"{int(RECENT_WEB_WINDOW.days)}d share phrasing with the "
                    f"filing's risk quote."
                ),
                basis=[e.evidence_id for e in supporting[:3]],
                classified_at=now,
            )

    # Rule 2: receding = no recent web AND contradicting web evidence exists.
    if contradicting_web and not recent_web:
        return RiskLifecycleAnnotation(
            risk_id=risk.risk_id,
            lifecycle="receding",
            confidence=0.65,
            reasoning=(
                "No recent web evidence; the available web evidence "
                "uses contradiction language ('abated', 'no longer', etc.)."
            ),
            basis=[e.evidence_id for e in contradicting_web[:3]],
            classified_at=now,
        )

    # Rule 3: emerging = web evidence mentions the same risk_factor but
    # the filing has no evidence_quote for it.
    if web_evidence and (not quote) and risk_factor:
        mentioning = [
            e
            for e in web_evidence
            if _factor_overlaps(risk_factor, e.quote)
        ]
        if mentioning:
            return RiskLifecycleAnnotation(
                risk_id=risk.risk_id,
                lifecycle="emerging",
                confidence=0.55,
                reasoning=(
                    f"{len(mentioning)} web evidence row(s) reference the "
                    f"risk but the 10-K does not quantify it — market is "
                    f"seeing it before the filing does."
                ),
                basis=[e.evidence_id for e in mentioning[:3]],
                classified_at=now,
            )

    # Default.
    if web_evidence:
        reasoning = "Web evidence exists but no rule fired; insufficient signal."
    else:
        reasoning = "No web evidence collected for this run."
    return RiskLifecycleAnnotation(
        risk_id=risk.risk_id,
        lifecycle="unknown",
        confidence=0.3,
        reasoning=reasoning,
        basis=[],
        classified_at=now,
    )


def _quote_overlaps(a: str, b: str, min_words: int = 4) -> bool:
    """Return True if ``a`` and ``b`` share at least ``min_words`` tokens."""
    a_tokens = {t.lower() for t in a.split() if len(t) > 3}
    b_tokens = {t.lower() for t in b.split() if len(t) > 3}
    return len(a_tokens & b_tokens) >= min_words


def _factor_overlaps(factor: str, text: str, min_chars: int = 12) -> bool:
    """Return True if a meaningful substring of ``factor`` appears in ``text``."""
    if not factor or not text:
        return False
    lower_factor = factor.lower()
    if len(lower_factor) < min_chars:
        # Short factors: require exact word match.
        words = {w.strip(".,;:") for w in lower_factor.split() if len(w) > 3}
        return any(w in text.lower() for w in words)
    # Long factors: require a 12-char substring to match.
    head = lower_factor[:min_chars]
    return head in text.lower()


__all__ = ["LifecycleClassifierStep"]