"""Rate-limit middleware tests (R1 supplement)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, reset_rate_limiter_for_tests
from src.api.rate_limit import SlidingWindowLimiter


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    """Clear rate-limit buckets between tests so the module-level
    limiter doesn't leak state across test cases."""
    reset_rate_limiter_for_tests()
    yield
    reset_rate_limiter_for_tests()


@pytest.fixture
def low_limit_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client configured with a 3 req/min limit so the test runs fast."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_API_KEYS", "rl-key")
    monkeypatch.setenv("RATE_LIMIT_RPM", "3")
    monkeypatch.setenv("RATE_LIMIT_BURST", "3")
    # ``RATE_LIMIT_DISABLED`` must not be set here.
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    return TestClient(app)


@pytest.fixture
def disabled_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with the limiter disabled — should never 429."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_API_KEYS", "rl-key")
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    return TestClient(app)


def test_under_limit_returns_200(low_limit_client: TestClient) -> None:
    headers = {"X-API-Key": "rl-key"}
    for _ in range(3):
        response = low_limit_client.get("/workflows/health", headers=headers)
        assert response.status_code == 200


def test_exceeding_limit_returns_429(low_limit_client: TestClient) -> None:
    headers = {"X-API-Key": "rl-key"}
    for _ in range(3):
        low_limit_client.get("/workflows/health", headers=headers)
    response = low_limit_client.get("/workflows/health", headers=headers)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) >= 1


def test_separate_keys_have_separate_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_API_KEYS", "key-a, key-b")
    monkeypatch.setenv("RATE_LIMIT_RPM", "2")
    monkeypatch.setenv("RATE_LIMIT_BURST", "2")
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    client = TestClient(app)
    # Exhaust bucket for key-a.
    for _ in range(2):
        client.get("/workflows/health", headers={"X-API-Key": "key-a"})
    blocked = client.get("/workflows/health", headers={"X-API-Key": "key-a"})
    assert blocked.status_code == 429
    # key-b is unaffected.
    allowed = client.get("/workflows/health", headers={"X-API-Key": "key-b"})
    assert allowed.status_code == 200


def test_disabled_limiter_never_429s(disabled_client: TestClient) -> None:
    headers = {"X-API-Key": "rl-key"}
    for _ in range(20):
        response = disabled_client.get("/workflows/health", headers=headers)
        assert response.status_code == 200


def test_limiter_unit_check() -> None:
    """Unit test that does not depend on the global env or HTTP stack."""
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
    allowed, wait = limiter.check("k", now=0.0)
    assert allowed and wait == 0
    allowed, wait = limiter.check("k", now=0.0)
    assert allowed and wait == 0
    allowed, wait = limiter.check("k", now=0.0)
    assert (allowed, wait) == (False, 61)
    # Move past the window — first hit expires.
    allowed, wait = limiter.check("k", now=61.0)
    assert allowed and wait == 0
    # Different keys do not share buckets.
    allowed, _ = limiter.check("other", now=61.0)
    assert allowed


def test_empty_key_is_a_noop() -> None:
    """An empty key never rejects — auth is the gate that matters here."""
    limiter = SlidingWindowLimiter(max_requests=1)
    for _ in range(5):
        allowed, _ = limiter.check("")
        assert allowed
