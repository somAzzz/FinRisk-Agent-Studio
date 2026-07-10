# Security — Known Limitations

This file tracks residual risks that the audit remediation does
**not** close. Each entry is something a future hardening pass
should address.

## DNS-rebinding (SSRF / R3)

`src/security/url_guard.py` resolves the hostname to an IP at
*validate-time* and rejects addresses that fall in the loopback /
link-local / private / multicast / reserved / unspecified ranges.
The HTTP client (`httpx` in `src/tools/web_fetch.py`) re-resolves
the hostname when it actually connects, so a DNS record that
flips between validation and connection can still land the request
on a private IP.

**Mitigation today**: in-process URL guard on every `web_fetch`
call. The window is bounded by the validate→connect round trip.

**Future fix**: pin DNS resolution at the transport level via
`httpx.AsyncHTTPTransport`. Out of scope for the audit pass.

## IDN / homograph attacks

`url_guard.py` does not normalise or block IDN hostnames. A
host like `аpple.com` (Cyrillic `а`) passes the guard and is
handed to `httpx` verbatim. The request is resolved by the system
DNS, which may or may not defend against homographs depending on
the resolver configuration.

**Future fix**: add `idna`-based normalisation and a Unicode
blocklist. Out of scope.

## Browser redirect re-validation

`src/browser/wrapper.py` validates the URL once at the entry
point of `navigate()`. The underlying `agent-browser` CLI follows
redirects freely; there is no hook to re-validate after each hop.

**Mitigation today**: validate pre-navigation; document the
residual risk here.

**Future fix**: switch to a Playwright backend where the
`page.on("response")` hook can re-validate every redirect. Out
of scope for the audit pass.

## Rate-limit memory growth (R1 supplement)

`RateLimitMiddleware` keeps one deque per (API key or IP) in
process memory. Long-running deployments accumulate buckets
indefinitely. Set `RATE_LIMIT_DISABLED=1` to disable the limiter
during a deploy if memory becomes a concern.

**Future fix**: a TTL-based eviction sweep, or move the limiter
to Redis.

## Single-process SQLite write concurrency (R2)

`SQLiteRunStore` serializes writes through `asyncio.Lock` and now
covers both FinRisk workflow runs and supply-chain runs when
`RUN_STORE_BACKEND=sqlite`. Multi-process deployments (multiple
uvicorn workers) will not see each other's writes in real time
because each worker holds its own SQLite connection. WAL mode
allows concurrent reads, but writes must wait for the writer's lock.

**Future fix**: Postgres / Redis for multi-process deployments.
Out of scope for the audit pass.

## LLM audit log redaction

`LLMCall` rows redact high-confidence patterns such as API keys,
tokens, email addresses, phone numbers, SSNs, and credit-card-like
numbers before they are persisted on workflow state. This is a
best-effort safety net, not a compliance-grade data-loss prevention
system: proprietary source text, uncommon secrets, or company-
specific confidential phrases can still appear in prompts and
responses.

**Future fix**: add tenant-specific redaction rules, log retention
policies, and an option to store only hashes / excerpts of prompts.
