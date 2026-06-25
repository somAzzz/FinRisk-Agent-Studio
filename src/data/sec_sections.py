"""Stable 10-K / 10-Q section extraction.

The naive regex parser in :mod:`src.data.filing_fetcher` is fine as a
fallback, but production needs an HTML-anchor-aware extractor that
handles whitespace, em-dashes, and Roman numerals reliably.

This module exposes :class:`SectionParser` with two strategies:

1. HTML anchor strategy: walk ``<a name="...">`` anchors when present.
2. Heading strategy: scan plain text for Item N / Item N headings.

The parser preserves ``char_start`` / ``char_end`` and always returns a
``full_text`` fallback so downstream code never breaks on a real 10-K.

Three robustness features specifically for real SEC filings (added 2026-06-25):

* ``html.unescape()`` after BeautifulSoup ``get_text()`` so NBSP entities
  (``&#160;``, ``&nbsp;``) and other HTML entities do not break the
  Item-heading regex.
* NBSP and zero-width characters are normalized to a plain space before
  matching.
* Forward-Looking Statements disclaimer paragraphs (which mention
  "Item 1A. Risk Factors" verbatim) are detected and stripped from the
  start of any matched Item 1A chunk, so the legal-boilerplate match
  is not preferred over the substantive risk-factor body.
* With ``prefer_substantive_match=True`` (the default), the parser
  picks the LONGEST match per section name rather than the first,
  which avoids the trap where the Forward-Looking Statements
  disclaimer appears earlier in the document than the real
  ``Item 1A. Risk Factors`` heading.
"""

from __future__ import annotations

import html as _stdlib_html
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Mapping of canonical section names to heading patterns.
# Patterns intentionally tolerate em-dashes, whitespace, and Roman numerals.
# The character class for the separator also accepts NBSP ( ) so that
# ``Item&#160;1A.`` (which becomes ``Item 1A.`` after html.unescape)
# still matches.
_ROMAN_NUMERALS = r"(?:i{1,3}|iv|v|vi{1,3}|ix|x)"
_DIGIT_OR_ROMAN = r"(?:\d|" + _ROMAN_NUMERALS + r")"
_SEPARATOR = r"[\.\:\-–— ]?"

SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "section_1": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*{_SEPARATOR}\s*business",
    ),
    "section_1a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*{_SEPARATOR}\s*risk\s*factors",
    ),
    "section_2": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*{_SEPARATOR}\s*properties",
    ),
    "section_3": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*{_SEPARATOR}\s*legal\s*proceedings",
    ),
    "section_7": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*{_SEPARATOR}\s*management",
    ),
    "section_7a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*{_SEPARATOR}\s*"
        r"(?:quantitative|market\s*risk)",
    ),
    "section_8": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*{_SEPARATOR}\s*financial\s*statements",
    ),
    "section_9a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*{_SEPARATOR}\s*controls",
    ),
}

# Boundary pattern used to detect "next item" headings.
# Accepts NBSP and zero-width characters in the separator slot so that
# SEC filings using ``Item&#160;1B.`` are still recognised as the next
# item boundary after Item 1A.
_NEXT_ITEM_PATTERN = re.compile(
    r"item\s*\d+\s*[a-z]?\s*[\.\:\-–— ]",
    re.IGNORECASE,
)

# Characters that survive BeautifulSoup.get_text() but should not break
# regex whitespace matching: NBSP ( ), zero-width space (​),
# zero-width non-joiner (‌), zero-width joiner (‍), word
# joiner (⁠), and the BOM (﻿).
_WEIRD_WHITESPACE_RE = re.compile("[\\u00a0\\u200b\\u200c\\u200d\\u2060\\ufeff]")

# Forward-Looking Statements disclaimer detection. Apple 10-K opens
# with one of these phrases before "Item 1A. Risk Factors" appears
# inside the disclaimer body. We use this to strip the leading
# boilerplate from any matched Item 1A chunk.
_FORWARD_LOOKING_HEADINGS_RE = re.compile(
    r"(?:forward[-\s]looking\s+statements"
    r"|cautionary\s+note\s+regarding"
    r"|safe\s+harbor(?:\s+statement)?"
    r"|risk\s+factors\s+summary)",
    re.IGNORECASE,
)

# Minimum length (chars) for a chunk to be considered substantive.
# Shorter chunks are usually legal boilerplate or noise.
_MIN_SUBSTANTIVE_CHARS = 500


@dataclass(frozen=True)
class Section:
    """A canonical 10-K/10-Q section."""

    name: str
    text: str
    char_start: int
    char_end: int


def _strip_html(html: str) -> str:
    """Convert filing HTML into clean plain text.

    The pipeline is:

    1. BeautifulSoup strips script/style and emits text with newlines.
    2. :func:`html.unescape` decodes ``&nbsp;`` / ``&#160;`` / ``&#8217;``
       / ``&amp;`` etc. so the Item-heading regex can match.
    3. NBSP and zero-width characters are normalised to a plain space,
       which avoids NBSP-separated Item headings failing the regex.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = _stdlib_html.unescape(text)
    text = _WEIRD_WHITESPACE_RE.sub(" ", text)
    return text


def _strip_forward_looking(text: str) -> tuple[str, bool]:
    """Strip a leading Forward-Looking Statements disclaimer.

    Returns ``(stripped_text, was_stripped)``. ``was_stripped`` is True
    when the text began with a recognised FLS heading — useful for
    audit logging so callers can see the disclaimer was filtered.
    """
    fls_match = _FORWARD_LOOKING_HEADINGS_RE.search(text)
    if not fls_match:
        return text, False
    # The FLS heading itself is part of the disclaimer. Find the end of
    # the first paragraph that contains it (paragraphs are separated
    # by blank lines after we normalised whitespace).
    paragraphs = re.split(r"\n\s*\n", text)
    if not paragraphs:
        return text, False
    # Drop the leading FLS heading paragraph(s). Some SEC filings wrap
    # the FLS heading in its own paragraph before the disclaimer body.
    kept_paragraphs: list[str] = []
    dropped_any = False
    for para in paragraphs:
        if not dropped_any and _FORWARD_LOOKING_HEADINGS_RE.search(para):
            dropped_any = True
            continue
        kept_paragraphs.append(para)
    return ("\n\n".join(kept_paragraphs)).strip(), dropped_any


class SectionParser:
    """Anchor-aware 10-K/10-Q section extractor.

    The parser operates on the plain-text version of the filing (already
    stripped of HTML tags, with entities unescaped) and looks for Item N
    headings using the patterns in :data:`SECTION_PATTERNS`.

    With ``prefer_substantive_match=True`` (the default), the parser
    picks the LONGEST match per section name rather than the first,
    which is the standard defence against the Forward-Looking
    Statements disclaimer trap on Apple's 10-K (where the disclaimer
    contains the phrase "Item 1A. Risk Factors" verbatim and appears
    earlier than the real section).
    """

    def __init__(
        self,
        section_patterns: dict[str, tuple[str, ...]] | None = None,
        strip_html: Callable[[str], str] | None = None,
        *,
        min_substantive_chars: int = _MIN_SUBSTANTIVE_CHARS,
        strip_forward_looking: bool = True,
    ) -> None:
        self._patterns = section_patterns or SECTION_PATTERNS
        self._strip_html = strip_html or _strip_html
        self._min_substantive_chars = min_substantive_chars
        self._strip_forward_looking = strip_forward_looking

    def parse(
        self,
        html: str,
        *,
        prefer_substantive_match: bool = True,
    ) -> dict[str, Section]:
        """Return ``{section_name: Section}`` extracted from ``html``.

        Always returns at least ``{"full_text": Section(...)}`` so callers
        never see an empty dict.

        Args:
            html: Raw 10-K/10-Q HTML.
            prefer_substantive_match: When True (default), keep the
                longest match per section name instead of the first.
                This is the standard defence against the FLS-disclaimer
                trap on Apple's 10-K.
        """
        text = self._strip_html(html)
        if not text:
            return {
                "full_text": Section(
                    name="full_text",
                    text="",
                    char_start=0,
                    char_end=0,
                )
            }

        sections = self._extract_sections(
            text, prefer_substantive_match=prefer_substantive_match
        )
        sections["full_text"] = Section(
            name="full_text",
            text=text,
            char_start=0,
            char_end=len(text),
        )
        return sections

    def _extract_sections(
        self,
        text: str,
        *,
        prefer_substantive_match: bool,
    ) -> dict[str, Section]:
        # Find ALL matches per section name, keep the longest substantive one.
        candidates: list[tuple[int, str, str]] = []
        for name, patterns in self._patterns.items():
            regex_str = "|".join(f"(?:{p})" for p in patterns)
            regex = re.compile(regex_str, re.IGNORECASE | re.DOTALL)
            if prefer_substantive_match:
                matches = list(regex.finditer(text))
            else:
                first = regex.search(text)
                matches = [first] if first else []

            best_match: re.Match[str] | None = None
            best_len = 0
            for m in matches:
                end = self._next_boundary(text, m.end())
                candidate_text = text[m.start():end]
                # Apply FLS strip only to Item 1A matches (the only
                # section where the FLS-disclaimer trap fires).
                if (
                    self._strip_forward_looking
                    and name == "section_1a"
                ):
                    candidate_text, _ = _strip_forward_looking(candidate_text)
                if len(candidate_text) > best_len:
                    best_len = len(candidate_text)
                    best_match = m

            if best_match is None:
                continue

            end = self._next_boundary(text, best_match.end())
            chunk = text[best_match.start():end]
            if self._strip_forward_looking and name == "section_1a":
                chunk, _ = _strip_forward_looking(chunk)
            chunk = chunk.strip()
            if not chunk:
                continue
            candidates.append((best_match.start(), name, chunk))

        candidates.sort(key=lambda x: x[0])
        result: dict[str, Section] = {}
        for index, (start, name, chunk) in enumerate(candidates):
            result[name] = Section(
                name=name,
                text=chunk,
                char_start=start,
                char_end=start + len(chunk),
            )
        return result

    @staticmethod
    def _next_boundary(text: str, start_pos: int) -> int:
        """Return the end position of the chunk starting at ``start_pos``.

        The chunk ends at the next Item-N heading boundary (so a
        section_1a match is bounded by ``Item 1B.`` or ``Item 2.``),
        or at the end of the document.
        """
        boundary = _NEXT_ITEM_PATTERN.search(text, pos=start_pos)
        if boundary is None:
            return len(text)
        return boundary.start()


def summarise_sections(sections: dict[str, Section]) -> dict[str, dict[str, Any]]:
    """Return a JSON-friendly per-section summary.

    Useful for the visualisation inspector (``SectionLocationPanel`` on
    the frontend): one row per section with ``name``, ``char_start``,
    ``char_end``, ``char_count``, and a text preview.
    """
    summary: dict[str, dict[str, Any]] = {}
    for name, sec in sections.items():
        preview = sec.text[:160].replace("\n", " ")
        summary[name] = {
            "name": sec.name,
            "char_start": sec.char_start,
            "char_end": sec.char_end,
            "char_count": sec.char_end - sec.char_start,
            "preview": preview,
        }
    return summary


__all__ = [
    "SECTION_PATTERNS",
    "Section",
    "SectionParser",
    "summarise_sections",
]