"""API authentication tests (R1).

These tests exercise the full HTTP stack via :class:`fastapi.testclient.TestClient`
so the ``Depends(require_api_key)`` middleware actually runs. Existing
handler-direct API tests bypass HTTP and therefore do not trigger
auth — they continue to work as long as the new dependency is wired
through FastAPI (not the handlers themselves).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with two valid keys configured and background execution off."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_API_KEYS", "secret-key-1, secret-key-2")
    return TestClient(app)


@pytest.fixture
def disabled_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with ``AUTH_DISABLED=1`` set — auth dependency bypassed."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.delenv("FINRISK_API_KEYS", raising=False)
    return TestClient(app)


@pytest.fixture
def empty_keys_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with no allowlist — should fail closed."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("FINRISK_API_KEYS", raising=False)
    return TestClient(app)


def test_missing_header_returns_401(authed_client: TestClient) -> None:
    response = authed_client.get("/workflows/health")
    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


def test_invalid_key_returns_401(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/workflows/health", headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "ApiKey"


def test_valid_key_returns_200(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/workflows/health", headers={"X-API-Key": "secret-key-1"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_second_valid_key_also_accepted(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/workflows/health", headers={"X-API-Key": "secret-key-2"}
    )
    assert response.status_code == 200


def test_auth_disabled_bypasses_dependency(disabled_client: TestClient) -> None:
    response = disabled_client.get("/workflows/health")
    assert response.status_code == 200


def test_empty_allowlist_fails_closed(empty_keys_client: TestClient) -> None:
    """An unset ``FINRISK_API_KEYS`` must NOT silently disable auth."""
    response = empty_keys_client.get("/workflows/health")
    assert response.status_code == 401
    body = response.json()
    assert "FINRISK_API_KEYS" in body["detail"]


def test_supply_chain_health_also_gated(authed_client: TestClient) -> None:
    response = authed_client.get("/supply-chain/health")
    assert response.status_code == 401


def test_supply_chain_health_accepts_key(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/supply-chain/health", headers={"X-API-Key": "secret-key-1"}
    )
    assert response.status_code == 200


def test_placeholder_keys_filtered_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """``REPLACE_ME``/``EMPTY``/``dummy`` style tokens must not authenticate."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_API_KEYS", "REPLACE_ME,EMPTY,dummy")
    client = TestClient(app)
    response = client.get(
        "/workflows/health", headers={"X-API-Key": "REPLACE_ME"}
    )
    assert response.status_code == 401
