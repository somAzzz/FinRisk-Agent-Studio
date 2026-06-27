"""V21 graph/browser evidence candidate normalization tests."""

from __future__ import annotations

import json

from src.evidence import EvidenceCandidateNormalizer
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


def _event(tool_name: str, data: dict) -> ToolExecutionEvent:
    return ToolExecutionEvent(
        event_id=f"event-{tool_name}",
        round_id="round-0",
        tool_call_id=f"call-{tool_name}",
        tool_name=tool_name,
        arguments={},
        status="success",
        result_summary=json.dumps(
            {"tool": tool_name, "status": "success", "data": data}
        ),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


def test_graph_path_event_becomes_graph_path_candidate() -> None:
    candidates = EvidenceCandidateNormalizer().normalize_event(
        _event(
            "graph_path_search",
            {
                "paths": [
                    {
                        "path_text": (
                            "AAPL depends on TSMC, exposing Apple supply chain "
                            "risk through Taiwan concentration."
                        ),
                        "evidence_ids": ["ev-1"],
                    }
                ]
            },
        ),
        related_text="Apple supply chain risk through TSMC Taiwan concentration",
    )

    assert len(candidates) == 1
    assert candidates[0].kind == "graph_path"
    assert candidates[0].status == "accepted"
    assert candidates[0].metadata["evidence_ids"] == ["ev-1"]


def test_browser_finding_becomes_browser_candidate() -> None:
    candidates = EvidenceCandidateNormalizer().normalize_event(
        _event(
            "browser_explore",
            {
                "findings": [
                    {
                        "url": "https://example.com/apple-suppliers",
                        "title": "Apple supplier page",
                        "summary": (
                            "Apple supplier evidence describes supply chain "
                            "dependency and supplier concentration."
                        ),
                    }
                ]
            },
        ),
        related_text="Apple supplier evidence supply chain dependency",
    )

    assert len(candidates) == 1
    assert candidates[0].kind == "browser"
    assert candidates[0].status == "accepted"
    assert candidates[0].source_url == "https://example.com/apple-suppliers"
