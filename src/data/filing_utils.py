"""Small helpers for working with raw filing rows."""

from __future__ import annotations

from collections.abc import Iterator

SECTION_PREFIX = "section_"


def iter_sections(row: dict) -> Iterator[tuple[str, str]]:
    """Yield ``(section_name, text)`` pairs for any key starting with ``section_``.

    Args:
        row: A mapping representing a single filing row.

    Yields:
        Tuples of ``(section_name, text)`` for every section-like key found.
    """
    for key, value in row.items():
        if isinstance(key, str) and key.startswith(SECTION_PREFIX):
            yield key, value if isinstance(value, str) else str(value)


def extract_year(value: object) -> int | None:
    """Convert a year-like value to ``int`` if possible, else ``None``.

    Accepts native ``int``, floats that are whole numbers, and numeric strings.
    Returns ``None`` for ``None`` inputs or anything that cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return None
    return None
