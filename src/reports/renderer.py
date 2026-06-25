"""Markdown renderer for structured risk reports."""

from __future__ import annotations

from src.reports.models import RiskReportV16


def render_risk_report_markdown(report: RiskReportV16) -> str:
    """Render a v16 report as deterministic markdown."""
    lines: list[str] = [
        f"# {report.title}",
        "",
        "## Executive Summary",
        "",
        report.executive_summary,
        "",
        "## Top Risks",
        "",
    ]
    if not report.top_risks:
        lines.extend(["No supported top risks were identified.", ""])
    for item in report.top_risks:
        lines.extend(
            [
                f"### {item.title}",
                "",
                f"- Risk ID: `{item.risk_id}`",
                f"- Type: {item.risk_type}",
                f"- Severity: {item.severity}/5",
                f"- Score: {item.final_score:.2f}/100",
                f"- Summary: {item.summary}",
                f"- Evidence: {', '.join(item.supporting_evidence_ids) or 'none'}",
                "",
            ]
        )

    if report.recent_changes:
        lines.extend(["## Recent Changes", ""])
        for change in report.recent_changes:
            lines.extend(
                [
                    f"- {change.text} "
                    f"(confidence {change.confidence:.2f}; evidence "
                    f"{', '.join(change.supporting_evidence_ids)})"
                ]
            )
        lines.append("")

    if report.second_order_effects:
        lines.extend(["## Second-Order Effects", ""])
        for insight in report.second_order_effects:
            affected = ", ".join(insight.affected_entities) or "unknown"
            lines.extend(
                [
                    f"- {affected}: {insight.explanation} "
                    f"(confidence {insight.confidence:.2f})"
                ]
            )
        lines.append("")

    lines.extend(["## Evidence References", ""])
    if not report.evidence_table:
        lines.extend(["No evidence references available.", ""])
    for evidence in report.evidence_table:
        source = evidence.source_name
        if evidence.source_url:
            source = f"[{source}]({evidence.source_url})"
        lines.extend(
            [
                f"- `{evidence.evidence_id}` {source}: "
                f"{evidence.quote_or_summary}",
            ]
        )
    lines.append("")

    lines.extend(["## Evidence vs Inference", ""])
    if not report.evidence_vs_inference:
        lines.extend(["No claims available.", ""])
    for claim in report.evidence_vs_inference:
        lines.extend(
            [
                f"- `{claim.claim_id}` ({claim.claim_type}, "
                f"confidence {claim.confidence:.2f}): {claim.text}",
            ]
        )
    lines.append("")

    lines.extend(["## Limitations", ""])
    if not report.limitations:
        lines.extend(["No limitations recorded.", ""])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")
    lines.append("")

    lines.extend(["## Recommended Next Questions", ""])
    if not report.recommended_next_questions:
        lines.extend(["No follow-up questions recorded.", ""])
    for question in report.recommended_next_questions:
        lines.append(f"- {question}")
    lines.extend(["", "## Disclaimer", "", report.disclaimer, ""])
    return "\n".join(lines)


__all__ = ["render_risk_report_markdown"]
