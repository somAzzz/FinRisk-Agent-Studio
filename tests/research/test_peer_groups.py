from __future__ import annotations

import pytest

from src.research.peer_groups import PeerGroupInput, PeerGroupStore, PeerMember


def _input() -> PeerGroupInput:
    return PeerGroupInput(
        name="Semiconductor leaders",
        base_ticker="NVDA",
        industry_template="semiconductor",
        members=[
            PeerMember(ticker="NVDA", inclusion_reason="Base company"),
            PeerMember(ticker="AMD", inclusion_reason="Accelerator competitor"),
        ],
    )


def test_peer_group_store_round_trip(tmp_path) -> None:
    store = PeerGroupStore(tmp_path / "research.sqlite")

    saved = store.save(_input())

    assert store.get(saved.peer_group_id) == saved
    assert store.list() == [saved]
    assert store.delete(saved.peer_group_id)
    assert store.list() == []


def test_peer_group_requires_base_and_confirmation() -> None:
    with pytest.raises(ValueError, match="base_ticker"):
        PeerGroupInput(
            name="Invalid",
            base_ticker="NVDA",
            members=[
                PeerMember(ticker="AMD", inclusion_reason="Competitor"),
                PeerMember(ticker="INTC", inclusion_reason="Competitor"),
            ],
        )
    with pytest.raises(ValueError, match="confirmed"):
        PeerGroupInput(
            name="Invalid suggestion",
            base_ticker="NVDA",
            members=[
                PeerMember(ticker="NVDA", inclusion_reason="Base"),
                PeerMember(
                    ticker="AMD",
                    inclusion_reason="Suggested from SIC",
                    source="suggested",
                    confirmed_by_user=False,
                ),
            ],
        )
