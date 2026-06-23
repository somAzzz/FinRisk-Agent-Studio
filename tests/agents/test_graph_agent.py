"""Tests for GraphReasoningAgent."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.graph_agent import GraphReasoningAgent
from src.agents.state import AgentState


def test_graph_agent_is_noop_without_client() -> None:
    """A missing client keeps the state untouched."""
    state = AgentState(goal="analyze AAPL", ticker="AAPL")
    out = GraphReasoningAgent().run(state)
    assert out is state
    assert out.notes == []


def test_graph_agent_handles_client_runtime_error(tmp_path: Path) -> None:
    """A client that raises during query is gracefully ignored."""

    class _BoomClient:
        def run(self, cypher, parameters=None):  # noqa: ANN001
            raise RuntimeError("graph offline")

    state = AgentState(goal="x", ticker="AAPL")
    out = GraphReasoningAgent(client=_BoomClient()).run(state)
    # No graph notes appended because every query raised.
    assert out is state


def test_graph_agent_appends_paths_and_entities() -> None:
    """Successful upstream queries append paths and entities."""

    supplier = SimpleNamespace(
        entity_id="sup",
        name="Supplier",
        entity_type="supplier",
        normalized_name="supplier",
        ticker=None,
        cik=None,
        aliases=[],
        metadata={},
        evidence=[],
        confidence=1.0,
    )
    acme = SimpleNamespace(
        entity_id="acme",
        name="Acme",
        entity_type="company",
        normalized_name="acme",
        ticker="ACME",
        cik="0001",
        aliases=[],
        metadata={},
        evidence=[],
        confidence=1.0,
    )
    path_obj = SimpleNamespace(
        nodes=[supplier, acme],
        relationships=[SimpleNamespace(type="SUPPLIES_TO")],
    )

    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list = []

        def run(self, cypher, parameters=None):  # noqa: ANN001
            self.calls.append(cypher)
            if "SUPPLIES_TO" in cypher or "BUYS_FROM" in cypher:
                return [{"p": path_obj}]
            return []

    client = _FakeClient()
    state = AgentState(goal="x", ticker="ACME")
    out = GraphReasoningAgent(client=client).run(state)
    assert any("upstream path" in n for n in out.notes)
    assert any(e.entity_id == "sup" for e in out.entities)
