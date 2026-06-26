"""URL guard / SSRF protection tests (R3).

The guard focuses on the **host** (IP-range / DNS resolution).
Scheme validation is the caller's responsibility. These tests
cover both the low-level :func:`check_host` and the
backwards-compat :func:`validate_url` shim.
"""

from __future__ import annotations

import pytest

from src.security.url_guard import (
    SSRFBlocked,
    check_host,
    validate_url,
)

# ---------------------------------------------------------------------------
# check_host — direct host checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.0.0.1:8080",  # port is part of the literal but treated as host
        "::1",
        "10.0.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
    ],
)
def test_check_host_blocks_private_and_loopback(host: str) -> None:
    with pytest.raises(SSRFBlocked):
        check_host(host)


def test_check_host_blocks_link_local_metadata() -> None:
    """The cloud metadata endpoint is at 169.254.169.254 — must be blocked."""
    with pytest.raises(SSRFBlocked, match="link-local"):
        check_host("169.254.169.254")


def test_check_host_blocks_ipv4_mapped_ipv6() -> None:
    with pytest.raises(SSRFBlocked):
        check_host("::ffff:127.0.0.1")


def test_check_host_allows_public_ip_literal() -> None:
    # 8.8.8.8 is Google Public DNS.
    check_host("8.8.8.8")


def test_check_host_allows_public_hostname() -> None:
    check_host("example.com")


def test_check_host_blocks_unresolvable_host() -> None:
    with pytest.raises(SSRFBlocked, match="cannot resolve"):
        check_host("this-host-definitely-does-not-exist.invalid")


def test_check_host_allow_private_bypasses() -> None:
    """Tests pointing at 127.0.0.1 stubs can opt out."""
    check_host("127.0.0.1", allow_private=True)


def test_check_host_empty_string_rejected() -> None:
    with pytest.raises(SSRFBlocked):
        check_host("")


# ---------------------------------------------------------------------------
# validate_url — backwards-compat full-URL entry point
# ---------------------------------------------------------------------------


def test_validate_url_extracts_host() -> None:
    """``validate_url`` is a thin wrapper around ``check_host``."""
    # This will trigger DNS resolution against example.com.
    validate_url("https://example.com/path?q=1")


def test_validate_url_unparseable_raises() -> None:
    """A string that urlparse cannot handle is reported as SSRF.
    The caller is expected to validate the scheme first; this
    function is the last line of defence."""
    with pytest.raises(SSRFBlocked):
        # urlparse("javascript:alert(1)") returns scheme="javascript",
        # netloc=""; we report a missing-host SSRF.
        validate_url("javascript:alert(1)")


def test_validate_url_allow_private_bypasses() -> None:
    validate_url("http://127.0.0.1:8000/", allow_private=True)
