"""Tests for :mod:`src.evaluation.report_eval`."""

from __future__ import annotations

from src.evaluation.report_eval import (
    FORBIDDEN_PHRASES,
    ReportEvalResult,
    evaluate_report,
)


SAMPLE_REPORT = """\
# Company Research Brief: DEMO

## Executive Summary

This research brief summarizes the available evidence and research
hypotheses for DEMO. It is not investment advice.

- Hypotheses generated: 1
- Supporting claims: 1 of 1
- Evidence records reviewed: 1 [1]

## Key Evidence

- [1] sec_filing: We face risks from supply chain disruptions and tariffs.

## Risks and Counter-Evidence

- [1] Risk factor disclosure.

## Sources

- [1] sec_filing: 10-K filing

Disclaimer: This report is for research only and is not investment advice.
"""


def test_disclaimer_detection() -> None:
    result = evaluate_report(SAMPLE_REPORT)
    assert isinstance(result, ReportEvalResult)
    assert result.disclaimer_exists is True


def test_citation_marker_detection() -> None:
    result = evaluate_report(SAMPLE_REPORT)
    assert result.every_claim_has_citation is True
    assert result.citation_marker_count >= 2


def test_counter_evidence_section_detection() -> None:
    result = evaluate_report(SAMPLE_REPORT)
    assert result.counter_evidence_exists is True


def test_forbidden_phrases_detected() -> None:
    text = "You should buy now, this stock is guaranteed to rise."
    result = evaluate_report(text)
    assert result.no_forbidden_phrases is False
    assert "buy now" in result.forbidden_phrases_found
    assert "guaranteed" in result.forbidden_phrases_found


def test_no_forbidden_phrases_in_clean_report() -> None:
    result = evaluate_report(SAMPLE_REPORT)
    assert result.no_forbidden_phrases is True
    assert result.forbidden_phrases_found == []


def test_chinese_forbidden_phrase_detected() -> None:
    text = "分析显示该股票必然上涨, 建议强烈买入。"
    result = evaluate_report(text)
    assert result.no_forbidden_phrases is False
    assert "必然上涨" in result.forbidden_phrases_found
    assert "强烈买入" in result.forbidden_phrases_found


def test_forbidden_phrase_constant_includes_all_known_phrases() -> None:
    expected_subset = {"buy now", "guaranteed", "must rise", "必然上涨", "强烈买入"}
    assert expected_subset.issubset(set(FORBIDDEN_PHRASES))
