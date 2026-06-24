"""Source quality validator.

Layered checks per v16 spec 02:

- Build a :class:`SourceQuality` row for every evidence row in
  the state.
- If a single source domain contributes more than three rows and
  diversity is low, emit a WARNING.
- If no primary source is present, emit a NEEDS_REVIEW.
- For each evidence row with ``credibility_score < 0.5`` emit a
  WARNING naming the evidence id.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.evaluation.source_quality import build_source_quality
from src.schemas.finrisk import FinRiskWorkflowState, NormalizedEvidence


def _domain(ev: NormalizedEvidence) -> str:
    url = (ev.source_url or "").strip().lower()
    if not url:
        return f"type:{ev.source_type}"
    try:
        return urlparse(url).netloc or f"type:{ev.source_type}"
    except ValueError:
        return f"type:{ev.source_type}"


class SourceQualityValidator:
    name = "source_quality"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        if not state.normalized_evidence:
            return []
        findings: list[GuardrailFinding] = []

        # Build a SourceQuality per evidence row and track domain counts.
        domain_counts: Counter[str] = Counter()
        primary_present = False
        for ev in state.normalized_evidence:
            quality = build_source_quality(
                source_url=ev.source_url or "",
                source_type=ev.source_type,
                collected_at=ev.collected_at,
            )
            if quality.is_primary_source:
                primary_present = True
            domain_counts[_domain(ev)] += 1
            if quality.credibility_score < 0.5:
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.NEEDS_REVIEW,
                        severity=GuardrailSeverity.WARNING,
                        message=(
                            f"evidence {ev.evidence_id} has low credibility "
                            f"({quality.credibility_score:.2f})"
                        ),
                        affected_object_type="source",
                        affected_object_id=ev.evidence_id,
                        recommendation="prefer a filing or financial-news source",
                    )
                )

        if not primary_present:
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.NEEDS_REVIEW,
                    severity=GuardrailSeverity.WARNING,
                    message="no primary source (filing/regulatory/company) found",
                    affected_object_type="workflow",
                )
            )

        # Diversity warning: a single domain > 3 rows AND > 50% of
        # total evidence count.
        total = sum(domain_counts.values())
        if total:
            top_domain, top_count = domain_counts.most_common(1)[0]
            if top_count > 3 and top_count / total > 0.5:
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.NEEDS_REVIEW,
                        severity=GuardrailSeverity.WARNING,
                        message=(
                            f"low source diversity: domain {top_domain!r} "
                            f"contributes {top_count}/{total} rows"
                        ),
                        affected_object_type="source",
                        affected_object_id=top_domain,
                    )
                )
        return findings


__all__ = ["SourceQualityValidator"]
