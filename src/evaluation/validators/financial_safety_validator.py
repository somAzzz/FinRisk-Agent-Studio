"""Financial safety validator: detect direct investment advice.

The validator scans the rendered report markdown (and the step
output, when it is itself markdown) for the v16 hard-advice
phrases defined in :mod:`src.workflows.evaluation`. A WARNING is
emitted for each occurrence; if more than one occurrence is
detected the status escalates to ``needs_review``.
"""

from __future__ import annotations

import re
from typing import Any

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.evaluation.validators.base import Validator
from src.schemas.finrisk import FinRiskWorkflowState
from src.workflows.evaluation import (
    _HARD_ADVICE_PATTERNS,
    _SOFT_ADVICE_PHRASES,
)


# A small compile-once cache so we don't re-evaluate the same
# markdown for every validator pass.
_HARD_PATTERNS: tuple[re.Pattern[str], ...] = _HARD_ADVICE_PATTERNS
_SOFT_PHRASES: tuple[str, ...] = _SOFT_ADVICE_PHRASES


def _scan(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, phrase)`` for every match in ``text``."""
    out: list[tuple[str, str]] = []
    if not text:
        return out
    for pat in _HARD_PATTERNS:
        m = pat.search(text)
        if m:
            out.append(("hard", m.group(0)))
    lowered = text.lower()
    for phrase in _SOFT_PHRASES:
        if phrase in lowered:
            out.append(("soft", phrase))
    return out


class FinancialSafetyValidator:
    name = "financial_safety"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        # Collect every string we want to scan.
        candidates: list[tuple[str, str]] = []
        if isinstance(output, str):
            candidates.append(("output", output))
        if state.report is not None:
            candidates.append(("report", state.report.markdown))
        if state.report is not None and state.report.executive_summary:
            candidates.append(("summary", state.report.executive_summary))

        findings: list[GuardrailFinding] = []
        for source, text in candidates:
            for kind, phrase in _scan(text):
                severity = (
                    GuardrailSeverity.ERROR
                    if kind == "hard"
                    else GuardrailSeverity.WARNING
                )
                status = (
                    GuardrailStatus.FAIL
                    if kind == "hard"
                    else GuardrailStatus.NEEDS_REVIEW
                )
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=status,
                        severity=severity,
                        message=f"{source} contains {kind} advice phrase: {phrase!r}",
                        affected_object_type="report_section",
                        affected_object_id=source,
                        recommendation="remove or paraphrase the phrase",
                    )
                )
        return findings


__all__ = ["FinancialSafetyValidator"]
