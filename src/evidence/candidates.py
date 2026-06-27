"""Normalize LLM tool execution events into evidence candidates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.evaluation.claim_grounding import lexical_overlap
from src.evaluation.source_quality import build_source_quality
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow

EvidenceCandidateStatus = Literal[
    "candidate",
    "accepted",
    "rejected",
    "needs_review",
]

EvidenceCandidateKind = Literal[
    "web",
    "filing",
    "transcript",
    "financial_metric",
    "graph_path",
    "browser",
]


class EvidenceCandidate(BaseModel):
    """One source-backed candidate extracted from a tool result."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_tool: str
    source_event_id: str
    kind: EvidenceCandidateKind
    source_url: str | None = None
    source_title: str | None = None
    quote: str | None = None
    summary: str
    entities: list[str] = Field(default_factory=list)
    related_subgoal_id: str | None = None
    related_risk_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    grounding_score: float = Field(default=0.5, ge=0.0, le=1.0)
    status: EvidenceCandidateStatus = "candidate"
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCandidateNormalizer:
    """Convert backend tool events into candidate evidence rows."""

    def normalize_events(
        self,
        events: list[ToolExecutionEvent],
        *,
        related_subgoal_id: str | None = None,
        related_text: str | None = None,
    ) -> list[EvidenceCandidate]:
        """Normalize multiple tool events and dedupe equivalent candidates."""
        candidates: list[EvidenceCandidate] = []
        for event in events:
            candidates.extend(
                self.normalize_event(
                    event,
                    related_subgoal_id=related_subgoal_id,
                    related_text=related_text,
                )
            )
        return _dedupe_candidates(candidates)

    def normalize_event(
        self,
        event: ToolExecutionEvent,
        *,
        related_subgoal_id: str | None = None,
        related_text: str | None = None,
    ) -> list[EvidenceCandidate]:
        """Normalize one tool event into zero or more candidates."""
        if event.status != "success":
            return [
                _rejected_candidate(
                    event,
                    reason=event.error or "tool execution failed",
                    related_subgoal_id=related_subgoal_id,
                )
            ]
        payload = _parse_payload(event.result_summary)
        if payload is None:
            return [
                _rejected_candidate(
                    event,
                    reason="tool result was not valid JSON",
                    related_subgoal_id=related_subgoal_id,
                )
            ]
        data = payload.get("data", payload)
        tool_name = str(payload.get("tool") or event.tool_name)
        rows = _rows_for_tool(tool_name, data)
        candidates = [
            _build_candidate(
                event,
                row,
                related_subgoal_id=related_subgoal_id,
                related_text=related_text,
            )
            for row in rows
        ]
        if not candidates:
            return [
                _rejected_candidate(
                    event,
                    reason="tool result did not contain source-backed evidence",
                    related_subgoal_id=related_subgoal_id,
                )
            ]
        return candidates


def _build_candidate(
    event: ToolExecutionEvent,
    row: dict[str, Any],
    *,
    related_subgoal_id: str | None,
    related_text: str | None,
) -> EvidenceCandidate:
    kind = row["kind"]
    source_url = _clean(row.get("source_url") or row.get("url"))
    summary = _compact(_clean(row.get("summary")) or _clean(row.get("quote")))
    quote = _compact(_clean(row.get("quote")) or summary)
    source_title = _clean(row.get("source_title") or row.get("title"))
    rejection_reason = _candidate_rejection_reason(kind, source_url, summary)
    quality = _source_quality_score(kind, source_url)
    grounding = _grounding_score(related_text, quote or summary)
    status: EvidenceCandidateStatus = "accepted"
    if rejection_reason is not None:
        status = "rejected"
    elif quality < 0.5:
        status = "rejected"
        rejection_reason = f"source quality below threshold ({quality:.2f})"
    elif grounding < 0.25:
        status = "needs_review"
        rejection_reason = f"grounding below threshold ({grounding:.2f})"
    return EvidenceCandidate(
        candidate_id=_candidate_id(event, kind, source_url, quote or summary),
        source_tool=event.tool_name,
        source_event_id=event.event_id,
        kind=kind,
        source_url=source_url,
        source_title=source_title,
        quote=quote,
        summary=summary or source_title or "",
        related_subgoal_id=related_subgoal_id,
        confidence=_confidence(status, quality, grounding),
        source_quality_score=quality,
        grounding_score=grounding,
        status=status,
        rejection_reason=rejection_reason,
        metadata={
            key: value
            for key, value in row.items()
            if key not in {"kind", "source_url", "url", "summary", "quote", "title"}
        },
    )


def _rejected_candidate(
    event: ToolExecutionEvent,
    *,
    reason: str,
    related_subgoal_id: str | None,
) -> EvidenceCandidate:
    summary = reason or "tool result rejected"
    return EvidenceCandidate(
        candidate_id=_candidate_id(event, "web", None, summary),
        source_tool=event.tool_name,
        source_event_id=event.event_id,
        kind="web",
        summary=summary,
        related_subgoal_id=related_subgoal_id,
        confidence=0.0,
        source_quality_score=0.0,
        grounding_score=0.0,
        status="rejected",
        rejection_reason=summary,
    )


def _parse_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _rows_for_tool(tool_name: str, data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    if tool_name == "search_and_fetch":
        return _web_search_rows(data.get("search", {})) + [
            row for page in data.get("fetched_pages", []) for row in _web_fetch_rows(page)
        ]
    if tool_name in {"financial_metrics_lookup", "xbrl_fact_lookup"}:
        return _financial_rows(data, tool_name=tool_name)
    if tool_name in {"graph_query", "graph_path_search"}:
        return _graph_rows(data)
    row_builders = {
        "web_search": _web_search_rows,
        "web_fetch": _web_fetch_rows,
        "sec_fetch_filing": _sec_filing_rows,
        "transcript_lookup": _transcript_rows,
        "browser_explore": _browser_rows,
    }
    builder = row_builders.get(tool_name)
    return builder(data) if builder is not None else []


def _web_search_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    return [
        {
            "kind": "web",
            "source_url": row.get("url"),
            "source_title": row.get("title"),
            "quote": row.get("snippet"),
            "summary": row.get("snippet"),
            "rank": row.get("rank"),
            "query": data.get("query"),
        }
        for row in data.get("results", [])
        if isinstance(row, dict)
    ]


def _web_fetch_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or data.get("status") == "failed":
        return []
    content = data.get("content") or data.get("description")
    return [
        {
            "kind": "web",
            "source_url": data.get("url"),
            "source_title": data.get("title"),
            "quote": content,
            "summary": content,
        }
    ]


def _sec_filing_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    text = data.get("text")
    return [
        {
            "kind": "filing",
            "source_url": data.get("source_url"),
            "source_title": data.get("form_type"),
            "quote": text,
            "summary": text,
            "accession_number": data.get("accession_number"),
            "section": data.get("section"),
        }
    ]


def _transcript_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for turn in data.get("turns", [])[:10]:
        if not isinstance(turn, dict):
            continue
        text = turn.get("text") or turn.get("content")
        rows.append(
            {
                "kind": "transcript",
                "source_url": data.get("url"),
                "source_title": data.get("title"),
                "quote": text,
                "summary": text,
                "speaker": turn.get("speaker"),
                "section": turn.get("section"),
            }
        )
    return rows


def _financial_rows(data: dict[str, Any], *, tool_name: str) -> list[dict[str, Any]]:
    values = data.get("metrics") or data.get("facts") or {}
    summary = json.dumps(values, ensure_ascii=False, default=str)
    return [
        {
            "kind": "financial_metric",
            "source_url": data.get("source_url"),
            "source_title": data.get("ticker") or tool_name,
            "quote": summary,
            "summary": summary,
            "ticker": data.get("ticker"),
        }
    ]


def _graph_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in data.get("paths", []) or []:
        if isinstance(path, dict):
            rows.append(
                {
                    "kind": "graph_path",
                    "source_title": "Graph path",
                    "quote": path.get("path_text"),
                    "summary": path.get("path_text"),
                    "evidence_ids": path.get("evidence_ids", []),
                }
            )
    return rows


def _browser_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in data.get("findings", []) or []:
        if isinstance(finding, dict):
            rows.append(
                {
                    "kind": "browser",
                    "source_url": finding.get("url"),
                    "source_title": finding.get("title"),
                    "quote": finding.get("summary"),
                    "summary": finding.get("summary"),
                }
            )
    return rows


def _candidate_rejection_reason(
    kind: EvidenceCandidateKind,
    source_url: str | None,
    summary: str,
) -> str | None:
    if not summary:
        return "candidate has no quote or summary"
    if kind in {"web", "transcript", "browser"} and not _valid_http_url(source_url):
        return "candidate has no valid http(s) source URL"
    return None


def _source_quality_score(kind: EvidenceCandidateKind, source_url: str | None) -> float:
    quality_type = {
        "web": "web",
        "browser": "web",
        "filing": "filing",
        "transcript": "transcript",
        "financial_metric": "filing",
        "graph_path": "graph",
    }[kind]
    quality = build_source_quality(
        source_url=source_url or "",
        source_type=quality_type,
        collected_at=utcnow(),
    )
    if kind == "graph_path":
        return max(0.5, quality.credibility_score)
    return quality.credibility_score


def _grounding_score(related_text: str | None, evidence_text: str) -> float:
    if not related_text:
        return 0.5
    return lexical_overlap(related_text, evidence_text)


def _confidence(
    status: EvidenceCandidateStatus,
    quality: float,
    grounding: float,
) -> float:
    if status == "rejected":
        return 0.0
    if status == "needs_review":
        return min(0.49, quality * 0.5 + grounding * 0.5)
    return min(1.0, quality * 0.6 + grounding * 0.4)


def _candidate_id(
    event: ToolExecutionEvent,
    kind: str,
    source_url: str | None,
    text: str,
) -> str:
    payload = f"{event.event_id}|{kind}|{source_url or ''}|{text[:200]}"
    digest = hashlib.sha1(payload.encode()).hexdigest()[:12]
    return f"evcand-{digest}"


def _dedupe_candidates(candidates: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
    out: list[EvidenceCandidate] = []
    seen: set[tuple[str, str | None, str]] = set()
    for candidate in candidates:
        key = (
            candidate.kind,
            candidate.source_url,
            (candidate.quote or candidate.summary)[:120],
        )
        if key in seen:
            continue
        out.append(candidate)
        seen.add(key)
    return out


def _compact(value: str, limit: int = 1000) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _valid_http_url(value: str | None) -> bool:
    return bool(value and value.startswith(("http://", "https://")))


__all__ = [
    "EvidenceCandidate",
    "EvidenceCandidateKind",
    "EvidenceCandidateNormalizer",
    "EvidenceCandidateStatus",
]
