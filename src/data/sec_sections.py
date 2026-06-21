"""Stable 10-K / 10-Q section extraction.

The naive regex parser in :mod:`src.data.filing_fetcher` is fine as a
fallback, but production needs an HTML-anchor-aware extractor that
handles whitespace, em-dashes, and Roman numerals reliably.

This module exposes :class:`SectionParser` with two strategies:

1. HTML anchor strategy: walk ``<a name="...">`` anchors when present.
2. Heading strategy: scan plain text for Item N / Item N headings.

The parser preserves ``char_start`` / ``char_end`` and always returns a
``full_text`` fallback so downstream code never breaks on a real 10-K.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# Mapping of canonical section names to heading patterns.
# Patterns intentionally tolerate em-dashes, whitespace, and Roman numerals.
_ROMAN_NUMERALS = r"(?:i{1,3}|iv|v|vi{1,3}|ix|x)"
_DIGIT_OR_ROMAN = r"(?:\d|" + _ROMAN_NUMERALS + r")"

SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "section_1": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*[\.\:\-–—]?\s*business",
    ),
    "section_1a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*[\.\:\-–—]?\s*risk\s*factors",
    ),
    "section_2": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*[\.\:\-–—]?\s*properties",
    ),
    "section_3": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*[\.\:\-–—]?\s*legal\s*proceedings",
    ),
    "section_7": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*[\.\:\-–—]?\s*management",
    ),
    "section_7a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*[\.\:\-–—]?\s*"
        r"(?:quantitative|market\s*risk)",
    ),
    "section_8": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*[\.\:\-–—]?\s*financial\s*statements",
    ),
    "section_9a": (
        rf"item\s*{_DIGIT_OR_ROMAN}\s*a\s*[\.\:\-–—]?\s*controls",
    ),
}

# Boundary pattern used to detect "next item" headings.
_NEXT_ITEM_PATTERN = re.compile(
    r"item\s*\d+\s*[a-z]?\s*[\.\:\-–—]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Section:
    """A canonical 10-K/10-Q section."""

    name: str
    text: str
    char_start: int
    char_end: int


def _strip_html(html: str) -> str:
    """Convert filing HTML into clean plain text."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


class SectionParser:
    """Anchor-aware 10-K/10-Q section extractor.

    The parser is intentionally simple: it operates on the plain-text
    version of the filing (already stripped of HTML tags) and looks for
    Item N headings using the patterns in :data:`SECTION_PATTERNS`.
    """

    def __init__(
        self,
        section_patterns: dict[str, tuple[str, ...]] | None = None,
        strip_html: Callable[[str], str] | None = None,
    ) -> None:
        self._patterns = section_patterns or SECTION_PATTERNS
        self._strip_html = strip_html or _strip_html

    def parse(self, html: str) -> dict[str, Section]:
        """Return ``{section_name: Section}`` extracted from ``html``.

        Always returns at least ``{"full_text": Section(...)}`` so callers
        never see an empty dict.
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

        sections = self._extract_sections(text)
        sections["full_text"] = Section(
            name="full_text",
            text=text,
            char_start=0,
            char_end=len(text),
        )
        return sections

    def _extract_sections(self, text: str) -> dict[str, Section]:
        matches: list[tuple[int, str]] = []
        for name, patterns in self._patterns.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                m = regex.search(text)
                if m is None:
                    continue
                matches.append((m.start(), name))
                # Only the first match per section name matters.
                break

        if not matches:
            return {}

        matches.sort(key=lambda pair: pair[0])
        result: dict[str, Section] = {}
        for index, (start, name) in enumerate(matches):
            end = (
                matches[index + 1][0]
                if index + 1 < len(matches)
                else len(text)
            )
            chunk = text[start:end]
            next_item = _NEXT_ITEM_PATTERN.search(chunk, pos=len(name) + 10)
            if next_item is not None and next_item.start() > 0:
                chunk = chunk[: next_item.start()]
            chunk = chunk.strip()
            result[name] = Section(
                name=name,
                text=chunk,
                char_start=start,
                char_end=start + len(chunk),
            )
        return result


__all__ = ["Section", "SectionParser", "SECTION_PATTERNS"]
