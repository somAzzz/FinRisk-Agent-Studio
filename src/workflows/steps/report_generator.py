"""Step 7: report generator.

Builds a ``RiskReport`` Pydantic model and renders the corresponding
markdown. The report deliberately excludes any direct buy / sell language
and separates evidence from inference.
"""

from __future__ import annotations

import logging

from src.workflows.state import (
    FinRiskWorkflowState,
    RiskReport,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

_FORBIDDEN_PHRASES = (
    "buy now",
    "must rise",
    "guaranteed",
    "guaranteed return",
    "sell now",
)


class ReportGeneratorStep(WorkflowStep):
    """Assemble a typed ``RiskReport`` and its markdown body."""

    name = "report_generator"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        company_name = (
            state.company.company_name if state.company else state.request.ticker
        )
        top_risks = sorted(
            state.filing_risks,
            key=lambda r: next(
                (
                    s.final_score
                    for s in state.risk_scores
                    if s.risk_id == r.risk_id
                ),
                0.0,
            ),
            reverse=True,
        )[:5]

        markdown = _render_markdown(
            ticker=state.request.ticker,
            company_name=company_name,
            goal=state.request.analysis_goal,
            top_risks=top_risks,
            scores=state.risk_scores,
            evidence=state.normalized_evidence,
            insights=state.graph_insights,
        )

        # Guardrail: scan the report for forbidden phrases before saving.
        lowered = markdown.lower()
        for phrase in _FORBIDDEN_PHRASES:
            if phrase in lowered:
                logger.warning(
                    "report contains forbidden phrase %r; stripping",
                    phrase,
                )
                markdown = markdown.replace(phrase, "[REDACTED]")

        evidence_summary = _render_evidence_table(state.normalized_evidence)
        evidence_vs_inference = (
            "**Evidence**: filing quotes and recent market/news reports "
            "that are cited verbatim above.\n"
            "**Inference**: the second-order paths in the graph insights "
            "section are inferred from those evidence rows using simple "
            "rules; they are not direct quotations.\n"
            "**Hypothesis**: future-state watchlist triggers derived from "
            "the inferred second-order effects; treat as research prompts, "
            "not as forecasts."
        )
        limitations = (
            "This brief is auto-generated from a small set of SEC 10-K "
            "and 10-Q filings plus a handful of news snippets. It does "
            "not include transcript evidence, deep graph reasoning, or "
            "macroeconomic time series. The risk scores are deterministic "
            "but their weights are heuristic; treat final scores as "
            "relative ordering signals, not as calibrated probabilities."
        )

        report = RiskReport(
            title=f"{company_name} Risk Intelligence Brief",
            executive_summary=_executive_summary(
                state.request.ticker, top_risks, state.risk_scores
            ),
            top_risks=top_risks,
            risk_scores=state.risk_scores,
            evidence_table=state.normalized_evidence,
            graph_insights=state.graph_insights,
            evidence_vs_inference=evidence_vs_inference,
            limitations=limitations,
            recommended_next_questions=[
                "Pull the most recent 8-K filings for material agreements.",
                "Compare supplier concentration across fiscal years.",
                "Add transcript sentiment when an API key is available.",
            ],
            markdown=markdown,
        )
        # Sanity check: every top_risk must have at least one normalized
        # evidence row referencing it. If not, drop those orphans so the
        # report only carries supported risks.
        risk_ids_with_evidence = {
            rid
            for ev in state.normalized_evidence
            for rid in (ev.related_risk_ids or [])
        }
        report = report.model_copy(
            update={
                "top_risks": [
                    r
                    for r in top_risks
                    if r.risk_id in risk_ids_with_evidence
                ]
            }
        )
        # Re-render markdown if any risks were dropped so the body stays
        # aligned with the top_risks list.
        if len(report.top_risks) < len(top_risks):
            report = report.model_copy(
                update={
                    "markdown": _render_markdown(
                        ticker=state.request.ticker,
                        company_name=company_name,
                        goal=state.request.analysis_goal,
                        top_risks=report.top_risks,
                        scores=state.risk_scores,
                        evidence=state.normalized_evidence,
                        insights=state.graph_insights,
                    )
                }
            )
        state.report = report
        return state


def _executive_summary(ticker: str, top_risks, scores) -> str:
    if not top_risks:
        return f"No filing risks identified for {ticker}."
    score_lines = [
        f"{scores[i].risk_id}={scores[i].final_score:.2f}"
        for i in range(min(len(top_risks), len(scores)))
    ]
    joined = ", ".join(score_lines)
    return (
        f"{ticker} top {len(top_risks)} risks (final scores: {joined}). "
        "Each risk is grounded in a SEC filing quote; see evidence table."
    )


def _render_evidence_table(evidence) -> str:
    if not evidence:
        return "No normalized evidence available."
    lines = [
        "| Evidence ID | Source | Type | Summary |",
        "|---|---|---|---|",
    ]
    for ev in evidence:
        summary = ev.summary.replace("|", "\\|").replace("\n", " ")
        source = ev.source_name.replace("|", "\\|")
        lines.append(
            f"| {ev.evidence_id} | {source} | {ev.source_type} | {summary} |"
        )
    return "\n".join(lines)


def _render_markdown(
    *,
    ticker: str,
    company_name: str,
    goal: str,
    top_risks,
    scores,
    evidence,
    insights,
) -> str:
    parts: list[str] = []
    parts.append(f"# {company_name} Risk Intelligence Brief")
    parts.append("")
    parts.append(f"_Analysis goal: {goal}_")
    parts.append("")

    # Executive summary
    parts.append("## Executive Summary")
    parts.append("")
    parts.append(_executive_summary(ticker, top_risks, scores))
    parts.append("")

    # Top risks
    parts.append("## Top Risks")
    parts.append("")
    if not top_risks:
        parts.append("No filing risks identified.")
    else:
        for risk in top_risks:
            score = next(
                (s.final_score for s in scores if s.risk_id == risk.risk_id),
                None,
            )
            score_text = (
                f" — final score {score:.2f}" if score is not None else ""
            )
            parts.append(f"### {risk.risk_id} ({risk.risk_type}){score_text}")
            parts.append("")
            parts.append(risk.risk_factor)
            parts.append("")
            parts.append(
                f"> \"{risk.evidence_quote}\" — {risk.source}"
            )
            parts.append("")

    # Recent changes / market signals
    parts.append("## Recent Changes")
    parts.append("")
    market = [e for e in evidence if e.source_type == "web"]
    if not market:
        parts.append("No recent market evidence collected.")
    else:
        for ev in market[:5]:
            parts.append(
                f"- [{ev.source_name}]({ev.source_url or 'n/a'}): {ev.summary}"
            )
    parts.append("")

    # Evidence table
    parts.append("## Evidence Table")
    parts.append("")
    parts.append(_render_evidence_table(evidence))
    parts.append("")

    # Second-order effects (graph)
    parts.append("## Second-Order Effects")
    parts.append("")
    if not insights:
        parts.append("No second-order graph insights identified.")
    else:
        for ins in insights:
            parts.append(
                f"- **{ins.source_company} → {ins.affected_entity}**: "
                f"{' → '.join(ins.risk_path)} (confidence {ins.confidence:.2f})"
            )
    parts.append("")

    parts.append("## Evidence vs Inference")
    parts.append("")
    parts.append(
        "**Evidence**: filing quotes and recent market/news reports that are "
        "cited verbatim above.\n"
        "**Inference**: the second-order paths in the graph insights section "
        "are inferred from those evidence rows using simple rules; they are "
        "not direct quotations.\n"
        "**Hypothesis**: future-state watchlist triggers derived from the "
        "inferred second-order effects; treat as research prompts, not as "
        "forecasts."
    )
    parts.append("")

    parts.append("## Confidence & Limitations")
    parts.append("")
    parts.append(
        "This brief is auto-generated from a small set of SEC 10-K and "
        "10-Q filings plus a handful of news snippets. It does not include "
        "transcript evidence, deep graph reasoning, or macroeconomic time "
        "series. The risk scores are deterministic but their weights are "
        "heuristic; treat final scores as relative ordering signals, not "
        "as calibrated probabilities."
    )
    parts.append("")

    parts.append("## Recommended Next Research Questions")
    parts.append("")
    parts.append("- Pull the most recent 8-K filings for material agreements.")
    parts.append("- Compare supplier concentration across fiscal years.")
    parts.append("- Add transcript sentiment when an API key is available.")
    parts.append("")
    parts.append("Disclaimer: This report is for research only and is not investment advice.")
    return "\n".join(parts)


__all__ = ["ReportGeneratorStep"]