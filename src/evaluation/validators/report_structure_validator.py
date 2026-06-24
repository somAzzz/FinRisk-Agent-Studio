"""Report structure validator: required sections and disclaimer.

The v16 spec demands four invariants in the final markdown:

- an Executive Summary section,
- a Top Risks section,
- a Disclaimer section,
- a Confidence & Limitations section.

The validator is opinionated about case (lower-case substring match
is enough; the markdown renderer capitalises consistently) and
about the disclaimer copy: it must contain the literal phrase
"not investment advice" so the report is legally clean.
"""

from __future__ import annotations

from typing import Any

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.evaluation.validators.base import Validator
from src.schemas.finrisk import FinRiskWorkflowState


_REQUIRED_SECTIONS: tuple[str, ...] = (
    "executive summary",
    "top risks",
    "confidence & limitations",
    "disclaimer",
)

_DISCLAIMER_PHRASE = "not investment advice"


def _has_section(markdown: str, section: str) -> bool:
    if not markdown:
        return False
    return section in markdown.lower()


class ReportStructureValidator:
    name = "report_structure"

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]:
        if state.report is None:
            return []
        findings: list[GuardrailFinding] = []
        markdown = state.report.markdown
        for section in _REQUIRED_SECTIONS:
            if not _has_section(markdown, section):
                findings.append(
                    GuardrailFinding(
                        step_name=step_name,
                        check_name=self.name,
                        status=GuardrailStatus.NEEDS_REVIEW,
                        severity=GuardrailSeverity.WARNING,
                        message=f"missing required section: {section!r}",
                        affected_object_type="report_section",
                        affected_object_id=section,
                        recommendation="add the section to the markdown body",
                    )
                )
        if markdown and _DISCLAIMER_PHRASE not in markdown.lower():
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=self.name,
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message="report is missing 'not investment advice' disclaimer",
                    affected_object_type="report_section",
                    affected_object_id="disclaimer",
                    recommendation="add the disclaimer copy to the markdown",
                )
            )
        return findings


__all__ = ["ReportStructureValidator"]
