"""v17 graph narrative safety tests.

The path interpreter must never emit language that could be
misread as a financial forecast or investment recommendation.
Each test in this file pins a forbidden phrase and asserts that
the scrubber removes it.
"""

from __future__ import annotations

from src.graph_reasoning import (
    FIXTURE_EDGES,
    FIXTURE_NODES,
    build_graph_context,
    interpret_paths,
    rank_paths,
    retrieve_candidate_paths,
)
from src.graph_reasoning.path_interpreter import (
    _FORBIDDEN_PHRASES,
    _scrub,
)
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


def _state() -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(
            ticker="AAPL", analysis_goal="supply chain", demo_mode=True
        ),
        normalized_evidence=[
            NormalizedEvidence(
                evidence_id="ne-1",
                source_type="filing",
                source_name="10-K",
                source_url=None,
                quote="Apple relies on Asian suppliers",
                summary="Apple supply chain",
                related_risk_ids=[],
                credibility_score=0.9,
                collected_at=utcnow(),
            )
        ],
    )


def test_scrub_removes_forbidden_phrases() -> None:
    for phrase in _FORBIDDEN_PHRASES:
        # Each phrase is replaced when surrounded by typical English
        # context; the scrubber matches on word boundaries so the
        # surrounding words must include a non-alphanumeric boundary
        # on each side.
        sentence = f"The analysis is {phrase} for everyone"
        out = _scrub(sentence)
        assert phrase not in out.lower(), (
            f"forbidden phrase {phrase!r} survived scrubbing: {out!r}"
        )


def test_scrub_replaces_phrase_with_redacted() -> None:
    out = _scrub("This is a strong buy recommendation")
    assert "strong buy" not in out.lower()
    assert "[REDACTED]" in out


def test_scrub_leaves_safe_text_unchanged() -> None:
    text = "Apple supply chain depends on TSMC located in Taiwan."
    assert _scrub(text) == text


def test_path_interpreter_does_not_emit_probability() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    insights = interpret_paths(ranked, state, top_k=1)
    assert insights
    text = insights[0].explanation.lower()
    assert "probability" not in text
    assert "guaranteed" not in text
    assert "buy" not in text
    assert "sell" not in text
    assert "should invest" not in text


def test_path_interpreter_uses_research_theme_not_investment_theme() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    insights = interpret_paths(ranked, state, top_k=1)
    assert insights
    # v17: only research_theme is allowed.
    assert insights[0].research_theme is not None
    # Pydantic field name ``research_theme`` is canonical.
    assert not hasattr(insights[0], "investment_theme")


def test_path_interpreter_includes_uncertainty_field() -> None:
    state = _state()
    ctx = build_graph_context(state)
    paths = retrieve_candidate_paths(ctx, nodes=FIXTURE_NODES, edges=FIXTURE_EDGES)
    ranked = rank_paths(paths, ctx, state)
    insights = interpret_paths(ranked, state, top_k=1)
    assert insights
    assert insights[0].uncertainty
    assert "no LLM judge" in insights[0].uncertainty
