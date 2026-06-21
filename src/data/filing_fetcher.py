"""Filing fetcher: list SEC filings and download their primary document HTML.

Wraps :class:`SECClient` to produce :class:`FilingMetadata` records and
:class:`FilingRecord` instances suitable for downstream analysis.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from bs4 import BeautifulSoup

from src.data.sec_client import SECClient  # noqa: F401  (used in type hint / runtime)
from src.schemas.filings import FilingMetadata, FilingRecord

_BASE_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"


def _build_filing_html_url(
    accession_number: str, cik: str, primary_doc: str
) -> str:
    """Construct the SEC Archives URL for a primary filing document.

    Mirrors :meth:`SECClient._build_filing_html_url` but lives here so callers
    that only need URL construction do not need to instantiate an SECClient.
    """
    accession_no_dashes = accession_number.replace("-", "")
    cik_int = int(cik)
    return (
        f"{_BASE_ARCHIVES_URL}/{cik_int}/"
        f"{accession_no_dashes}/{primary_doc}"
    )

# Section patterns used by the naive parser. These are deliberately
# conservative — many real 10-Ks use typographic whitespace, em dashes, or
# roman numerals, so the matches are intentionally broad.
_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "section_1": re.compile(
        r"item\s*1\s*[\.\:\-]?\s*business", re.IGNORECASE
    ),
    "section_1a": re.compile(
        r"item\s*1\s*a\s*[\.\:\-]?\s*risk\s*factors", re.IGNORECASE
    ),
    "section_7": re.compile(
        r"item\s*7\s*[\.\:\-]?\s*management", re.IGNORECASE
    ),
    "section_7a": re.compile(
        r"item\s*7\s*a\s*[\.\:\-]?\s*quantitative", re.IGNORECASE
    ),
}

# A small, conservative set of "next-item" markers used to bound a section.
_NEXT_ITEM_PATTERN = re.compile(
    r"item\s*\d+\s*[a-z]?\s*[\.\:\-]", re.IGNORECASE
)


def _extract_sections(text: str) -> dict[str, str]:
    """Extract canonical 10-K Item sections using naive regex matching.

    TODO: This is intentionally simple. Filings vary widely in formatting
    (em-dashes, whitespace, roman numerals). Replace with a more robust
    parser (e.g. an Item-aware tokenizer or a small model) before relying on
    these sections in production.
    """
    sections: dict[str, str] = {}
    matches: list[tuple[int, str]] = []
    for name, pattern in _SECTION_PATTERNS.items():
        match = pattern.search(text)
        if match is not None:
            matches.append((match.start(), name))
    if not matches:
        return sections
    matches.sort()
    for index, (start, name) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        chunk = text[start:end]
        # Trim the chunk to the next item marker if present.
        next_item = _NEXT_ITEM_PATTERN.search(chunk, pos=len(name) + 10)
        if next_item is not None and next_item.start() > 0:
            chunk = chunk[: next_item.start()]
        sections[name] = chunk.strip()
    return sections


class FilingFetcher:
    """High-level helper for discovering and downloading SEC filings."""

    def __init__(self, sec_client: SECClient) -> None:
        self.sec_client = sec_client

    def list_filings(
        self,
        cik: str,
        form_types: Sequence[str] = ("10-K", "10-Q", "8-K"),
        since: date | None = None,
        limit: int | None = None,
    ) -> list[FilingMetadata]:
        """Return :class:`FilingMetadata` records for the given CIK.

        Args:
            cik: Central Index Key, with or without leading zeros.
            form_types: Form types to keep, e.g. ``("10-K", "10-Q")``.
            since: Drop filings filed strictly before this date.
            limit: Cap the number of returned records (post-filtering).
        """
        payload = self.sec_client.get_submissions(cik)
        recent = payload.get("filings", {}).get("recent", {})
        accession_numbers: list[str] = recent.get("accessionNumber", []) or []
        forms: list[str] = recent.get("form", []) or []
        filing_dates: list[str] = recent.get("filingDate", []) or []
        report_dates: list[str] = recent.get("reportDate", []) or []
        primary_docs: list[str] = recent.get("primaryDocument", []) or []
        cik10 = SECClient.pad_cik(cik)

        wanted_forms = {form.upper() for form in form_types}
        results: list[FilingMetadata] = []
        for idx, accession in enumerate(accession_numbers):
            if idx >= len(forms):
                break
            form = (forms[idx] or "").upper()
            if wanted_forms and form not in wanted_forms:
                continue
            filing_date_str = filing_dates[idx] if idx < len(filing_dates) else ""
            if not filing_date_str:
                continue
            try:
                filing_date_value = date.fromisoformat(filing_date_str)
            except ValueError:
                continue
            if since is not None and filing_date_value < since:
                continue
            report_date_value: date | None = None
            if idx < len(report_dates) and report_dates[idx]:
                try:
                    report_date_value = date.fromisoformat(report_dates[idx])
                except ValueError:
                    report_date_value = None
            primary_document = (
                primary_docs[idx] if idx < len(primary_docs) else ""
            )
            url = _build_filing_html_url(accession, cik10, primary_document)
            results.append(
                FilingMetadata(
                    cik=cik10,
                    accession_number=accession,
                    form_type=form,
                    filing_date=filing_date_value,
                    report_date=report_date_value,
                    primary_document=primary_document,
                    url=url,
                )
            )
            if limit is not None and len(results) >= limit:
                break
        return results

    def fetch_filing(self, metadata: FilingMetadata) -> FilingRecord:
        """Download and parse a single filing into a :class:`FilingRecord`."""
        html = self.sec_client.get_filing_html(
            metadata.accession_number,
            metadata.cik,
            metadata.primary_document,
        )
        soup = BeautifulSoup(html, "html.parser")
        # Drop script/style noise that pollutes text extraction.
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        sections = {"full_text": text}
        # Attempt naive item extraction. Failures are non-fatal.
        try:
            extracted = _extract_sections(text)
        except Exception:  # noqa: BLE001 — defensive: never fail on parsing
            extracted = {}
        sections.update(extracted)
        return FilingRecord(
            source="sec",
            cik=metadata.cik,
            form_type=metadata.form_type,
            filing_date=metadata.filing_date,
            accession_number=metadata.accession_number,
            sections=sections,
            url=metadata.url,
            metadata={
                "primary_document": metadata.primary_document,
                "report_date": (
                    metadata.report_date.isoformat()
                    if metadata.report_date is not None
                    else None
                ),
            },
        )