"""Thin HTTP client for the SEC EDGAR public APIs.

Provides :class:`SECClient`, a small wrapper around ``requests.Session`` that
honors SEC's fair-access rules: every request carries a User-Agent header and
requests are throttled to at most ``rate_limit_per_second`` calls per second.

Errors are mapped to custom exceptions so callers can handle 404, 429, and
generic HTTP failures without touching the underlying ``requests`` library.
"""

from __future__ import annotations

import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings


class SECClientError(Exception):
    """Base class for all errors raised by :class:`SECClient`."""


class SECRateLimitError(SECClientError):
    """Raised when the SEC API signals a 429 / rate-limit response."""


class SECNotFoundError(SECClientError):
    """Raised when a requested SEC resource returns HTTP 404."""


class SECHTTPError(SECClientError):
    """Raised for any other non-success HTTP response from the SEC."""


class SECClient:
    """Minimal SEC EDGAR HTTP client with retries, throttling, and typed errors.

    Args:
        user_agent: Identifying string for the SEC fair-access policy. Falls
            back to ``Settings.sec_user_agent`` when ``None``.
        rate_limit_per_second: Maximum number of requests per second. Falls
            back to ``Settings.sec_rate_limit_per_second`` when ``None``.
        timeout: Per-request timeout in seconds.
    """

    BASE_DATA_URL = "https://data.sec.gov"
    BASE_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

    def __init__(
        self,
        user_agent: str | None = None,
        rate_limit_per_second: float | None = None,
        timeout: float = 20.0,
    ) -> None:
        settings = get_settings()
        self.user_agent: str = user_agent or settings.sec_user_agent
        if rate_limit_per_second is None:
            rate_limit_per_second = settings.sec_rate_limit_per_second
        self.rate_limit_per_second: float = float(rate_limit_per_second)
        self.timeout: float = timeout

        self._session: requests.Session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "data.sec.gov",
            }
        )

        # Track the last call timestamp so we can throttle to the desired rate.
        self._last_call_ts: float | None = None

    @property
    def session(self) -> requests.Session:
        """Return the underlying ``requests.Session`` (mainly for tests)."""
        return self._session

    def _wait_for_slot(self) -> None:
        """Sleep, if needed, so the next call respects ``rate_limit_per_second``.

        The minimum spacing between two calls is ``1 / rate_limit_per_second``
        seconds. A small floor of 1e-6 seconds avoids division-by-zero when
        callers configure an absurdly high rate.
        """
        if self.rate_limit_per_second <= 0:
            return
        min_interval = 1.0 / self.rate_limit_per_second
        now = time.monotonic()
        if self._last_call_ts is not None:
            elapsed = now - self._last_call_ts
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._last_call_ts = time.monotonic()

    @staticmethod
    def pad_cik(cik: str) -> str:
        """Return the 10-digit zero-padded form of a CIK."""
        return str(cik).strip().zfill(10)

    def _build_submissions_url(self, cik: str) -> str:
        cik10 = self.pad_cik(cik)
        return f"{self.BASE_DATA_URL}/submissions/CIK{cik10}.json"

    def _build_company_facts_url(self, cik: str) -> str:
        cik10 = self.pad_cik(cik)
        return f"{self.BASE_DATA_URL}/api/xbrl/companyfacts/CIK{cik10}.json"

    def _build_company_concept_url(self, cik: str, taxonomy: str, tag: str) -> str:
        cik10 = self.pad_cik(cik)
        return (
            f"{self.BASE_DATA_URL}/api/xbrl/companyconcept/"
            f"CIK{cik10}/{taxonomy}/{tag}.json"
        )

    def _build_filing_html_url(
        self, accession_number: str, cik: str, primary_doc: str
    ) -> str:
        accession_no_dashes = accession_number.replace("-", "")
        cik_int = int(cik)
        return (
            f"{self.BASE_ARCHIVES_URL}/{cik_int}/"
            f"{accession_no_dashes}/{primary_doc}"
        )

    def build_filing_document_url(
        self, cik: str, accession_number: str, primary_document: str
    ) -> str:
        """Build the public Archives URL for a filing primary document."""
        return self._build_filing_html_url(accession_number, cik, primary_document)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _request(self, url: str) -> dict:
        """Issue a GET request, returning the parsed JSON body.

        Retries up to 3 times on transient errors with exponential backoff.
        HTTP errors are mapped to :class:`SECClientError` subclasses.
        """
        self._wait_for_slot()
        # EDGAR serves both subdomains; switch the Host header to match.
        self._session.headers["Host"] = requests.utils.urlparse(url).netloc
        response = self._session.get(url, timeout=self.timeout)
        status = response.status_code
        if status == 404:
            raise SECNotFoundError(f"Resource not found at {url}")
        if status == 429:
            raise SECRateLimitError(f"Rate limited by SEC at {url}")
        if status >= 400:
            raise SECHTTPError(
                f"SEC request failed with status {status} at {url}"
            )
        return response.json()

    def get_submissions(self, cik: str) -> dict:
        """Return the submissions JSON for the given CIK.

        See: https://data.sec.gov/submissions/CIK{cik}.json
        """
        url = self._build_submissions_url(cik)
        return self._request(url)

    def get_company_facts(self, cik: str) -> dict:
        """Return the XBRL company facts JSON for the given CIK.

        See: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
        """
        url = self._build_company_facts_url(cik)
        return self._request(url)

    def get_company_concept(
        self,
        cik: str,
        taxonomy: str = "us-gaap",
        tag: str = "Assets",
    ) -> dict:
        """Return one XBRL company concept for a CIK/taxonomy/tag.

        See: https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json
        """
        url = self._build_company_concept_url(cik, taxonomy, tag)
        return self._request(url)

    def get_company_tickers(self) -> dict[str, dict]:
        """Return SEC's public ticker -> CIK mapping payload."""
        return self._request(self.COMPANY_TICKERS_URL)

    def ticker_to_cik(self, ticker: str) -> str:
        """Resolve a ticker to a 10-digit CIK using SEC's ticker mapping."""
        ticker_upper = ticker.upper().strip()
        payload = self.get_company_tickers()
        for entry in payload.values():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("ticker", "")).upper() != ticker_upper:
                continue
            raw_cik = entry.get("cik_str")
            if raw_cik is None:
                break
            return self.pad_cik(str(raw_cik))
        raise SECNotFoundError(f"Ticker not found in SEC company_tickers: {ticker}")

    def get_filing_html(
        self, accession_number: str, cik: str, primary_doc: str
    ) -> str:
        """Return the raw HTML body of the primary filing document."""
        url = self._build_filing_html_url(accession_number, cik, primary_doc)
        self._wait_for_slot()
        # Switch Host header for the archives subdomain.
        self._session.headers["Host"] = requests.utils.urlparse(url).netloc
        response = self._session.get(url, timeout=self.timeout)
        status = response.status_code
        if status == 404:
            raise SECNotFoundError(f"Filing not found at {url}")
        if status == 429:
            raise SECRateLimitError(f"Rate limited by SEC at {url}")
        if status >= 400:
            raise SECHTTPError(
                f"SEC request failed with status {status} at {url}"
            )
        return response.text
