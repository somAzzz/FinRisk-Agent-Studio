"""Tests for V21 evidence candidate normalization."""

from __future__ import annotations

import json

from src.evidence import EvidenceCandidateNormalizer
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


def _event(
    tool_name: str,
    payload: dict | str,
    *,
    status: str = "success",
    event_id: str = "event-1",
) -> ToolExecutionEvent:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ToolExecutionEvent(
        event_id=event_id,
        round_id="round-0",
        tool_call_id=f"call-{event_id}",
        tool_name=tool_name,
        arguments={},
        status=status,  # type: ignore[arg-type]
        result_summary=content,
        latency_ms=1,
        error=None if status == "success" else "boom",
        result_chars=len(content),
        created_at=utcnow(),
    )


def _envelope(tool: str, data: dict) -> dict:
    return {
        "tool": tool,
        "status": "success",
        "data": data,
        "warnings": [],
        "truncated": False,
    }


def test_web_search_event_becomes_accepted_candidate() -> None:
    normalizer = EvidenceCandidateNormalizer()
    event = _event(
        "web_search",
        _envelope(
            "web_search",
            {
                "query": "Apple supply chain",
                "results": [
                    {
                        "title": "Apple supplier pressure",
                        "url": "https://example.com/apple",
                        "snippet": "Apple supplier pressure affects supply chain planning.",
                        "rank": 1,
                    }
                ],
            },
        ),
    )

    candidates = normalizer.normalize_event(
        event,
        related_text="Apple supplier pressure supply chain",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == "web"
    assert candidate.status == "accepted"
    assert candidate.source_url == "https://example.com/apple"
    assert candidate.source_tool == "web_search"


def test_web_fetch_event_without_url_is_rejected() -> None:
    candidates = EvidenceCandidateNormalizer().normalize_event(
        _event(
            "web_fetch",
            _envelope(
                "web_fetch",
                {"title": "No URL", "content": "Useful but unsourced content."},
            ),
        )
    )

    assert candidates[0].status == "rejected"
    assert "valid http" in candidates[0].rejection_reason


def test_transcript_event_becomes_transcript_candidate() -> None:
    event = _event(
        "transcript_lookup",
        _envelope(
            "transcript_lookup",
            {
                "url": "https://example.com/transcript",
                "title": "Q1 call",
                "turns": [
                    {
                        "speaker": "CFO",
                        "section": "qa",
                        "text": "We are managing supplier availability carefully.",
                    }
                ],
            },
        ),
    )

    candidate = EvidenceCandidateNormalizer().normalize_event(event)[0]

    assert candidate.kind == "transcript"
    assert candidate.status == "accepted"
    assert candidate.metadata["speaker"] == "CFO"


def test_graph_path_event_without_url_can_be_accepted() -> None:
    event = _event(
        "graph_path_search",
        _envelope(
            "graph_path_search",
            {
                "paths": [
                    {
                        "path_text": "Apple Inc. -> TSMC -> Taiwan",
                        "evidence_ids": ["ev-1"],
                    }
                ]
            },
        ),
    )

    candidate = EvidenceCandidateNormalizer().normalize_event(event)[0]

    assert candidate.kind == "graph_path"
    assert candidate.status == "accepted"
    assert candidate.summary == "Apple Inc. -> TSMC -> Taiwan"


def test_browser_event_becomes_browser_candidate() -> None:
    event = _event(
        "browser_explore",
        _envelope(
            "browser_explore",
            {
                "findings": [
                    {
                        "url": "https://example.com/browser",
                        "summary": "Browser found source-backed supplier evidence.",
                    }
                ]
            },
        ),
    )

    candidate = EvidenceCandidateNormalizer().normalize_event(event)[0]

    assert candidate.kind == "browser"
    assert candidate.status == "accepted"


def test_failed_tool_event_becomes_rejected_candidate() -> None:
    event = _event("web_search", {"error": "boom"}, status="failed")

    candidate = EvidenceCandidateNormalizer().normalize_event(event)[0]

    assert candidate.status == "rejected"
    assert candidate.rejection_reason == "boom"


def test_duplicate_candidates_are_merged() -> None:
    payload = _envelope(
        "web_search",
        {
            "query": "Apple",
            "results": [
                {
                    "title": "A",
                    "url": "https://example.com/a",
                    "snippet": "Apple supplier pressure appears in both rows.",
                    "rank": 1,
                }
            ],
        },
    )
    event_1 = _event("web_search", payload, event_id="event-1")
    event_2 = _event("web_search", payload, event_id="event-2")

    candidates = EvidenceCandidateNormalizer().normalize_events([event_1, event_2])

    assert len(candidates) == 1
