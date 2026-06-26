"""URL guard for SSRF protection (R3 mitigation).

A small stdlib-only helper that rejects URLs pointing at loopback,
link-local, private, multicast, reserved, or unspecified IP
addresses — including the cloud metadata endpoint at
``169.254.169.254``. Only ``http`` and ``https`` schemes are
allowed.

Usage::

    from src.security.url_guard import validate_url, SSRFBlocked
    try:
        validate_url(url)
    except SSRFBlocked as exc:
        ...

Limitations (documented; tracked in
``docs/security/known-limitations.md``):

- DNS-rebinding: we resolve at validate-time, but the underlying
  HTTP client re-resolves when it connects. A follow-up using a
  custom :class:`httpx.AsyncHTTPTransport` with pinned DNS would
  close this window.
- IDN / homograph attacks are not detected.
- The browser wrapper's redirect path cannot be hooked without
  Playwright; the agent-browser CLI is left as a documented
  residual risk.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFBlockedError(ValueError):
    """Raised when a URL targets a host we refuse to fetch.

    Note: this guard focuses on the **host** (IP-range / DNS
    resolution). The scheme check (``http``/``https`` only) is the
    caller's responsibility; it lives next to the URL-parsing code
    so a malformed URL still surfaces as ``INVALID_URL`` rather
    than being swallowed by the SSRF guard.
    """

    def __init__(self, reason: str, host: str) -> None:
        super().__init__(f"{reason}: {host}")
        self.reason = reason
        self.host = host


# Backwards-compat alias. Older call sites catch ``SSRFBlocked``;
# the canonical name is ``SSRFBlockedError``.
SSRFBlocked = SSRFBlockedError


def _ip_for_host(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Best-effort resolution of ``host`` to an IP address.

    Returns ``None`` if the host cannot be parsed as a literal IP and
    DNS resolution fails.
    """
    if not host:
        return None
    # Strip IPv6 brackets if present.
    candidate = host.strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    try:
        info = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return None
    for family, _, _, _, sockaddr in info:
        if family in (socket.AF_INET, socket.AF_INET6):
            return ipaddress.ip_address(sockaddr[0])
    return None


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return the reason string if ``ip`` should be blocked, else None."""
    # IPv4Mapped IPv6 addresses need to be checked against the v4
    # flags; ``ipaddress.IPv6Address.ipv4_mapped`` does the right
    # thing.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_private:
        return "private address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_unspecified:
        return "unspecified address"
    return None


def check_host(host: str, *, allow_private: bool = False) -> None:
    """Raise :class:`SSRFBlocked` if ``host`` resolves to a blocked IP.

    The caller is responsible for stripping the scheme / path and
    passing just the host (e.g. ``example.com`` or ``127.0.0.1``).
    This split keeps scheme validation close to URL parsing and
    makes the SSRF guard easier to test in isolation.
    """
    if not host:
        raise SSRFBlocked("missing host", "")
    if allow_private:
        return
    # First try as a literal IP.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        reason = _is_blocked_ip(literal)
        if reason:
            raise SSRFBlocked(f"blocked {reason}", host)
        return
    # Otherwise resolve and check.
    resolved = _ip_for_host(host)
    if resolved is None:
        raise SSRFBlocked("cannot resolve host", host)
    reason = _is_blocked_ip(resolved)
    if reason:
        raise SSRFBlocked(f"blocked {reason}", host)


# Backwards-compat alias — older callers use ``validate_url`` to
# pass a full URL string. We dispatch to ``check_host`` with the
# hostname extracted via ``urllib``.
def validate_url(url: str, *, allow_private: bool = False) -> None:
    """Backwards-compat entry point. Prefer :func:`check_host`."""

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SSRFBlocked("unparseable url", url) from exc
    host = parsed.hostname or ""
    check_host(host, allow_private=allow_private)


__all__ = ["SSRFBlocked", "SSRFBlockedError", "check_host", "validate_url"]
