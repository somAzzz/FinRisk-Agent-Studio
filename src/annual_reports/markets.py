"""Acquire dated market publications and optional tabular/API observations."""

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.annual_reports.documents import MAX_BYTES, Document, DocumentError, Page, download, extract, is_pdf


def market_publication(url: str) -> Document:
    payload, source = download(url, discover_pdf=False)
    if is_pdf(payload) or payload.startswith(b"PK"):
        return extract(payload, source)
    if len(payload) > MAX_BYTES // 4:
        raise DocumentError("Market feed is too large; request a bounded observation period")
    text = payload.decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        html = BeautifulSoup(text, "html.parser")
        for tag in html.select("script,style,nav,footer"):
            tag.decompose()
        body = html.find("article") or html.find("main") or html.body
        if body is None:
            raise DocumentError("Expected a market article or table")
        text = body.get_text(" ", strip=True)
    elif text.lstrip().startswith(("{", "[")):
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    if not text.strip():
        raise DocumentError("Empty market publication")
    return Document(source, hashlib.sha256(payload).hexdigest(), [Page(1, None, text, "market_feed")])


class MarketSeries(BaseModel):
    """One versioned data release. Dates refer to its publication and observations, respectively."""

    model_config = ConfigDict(extra="forbid")
    driver: Literal["sugar_price", "trade", "weather", "grain_price", "energy_price", "other"]
    segment: str
    region: str
    unit: str
    url: HttpUrl
    published_at: date
    date_column: str
    value_column: str
    delimiter: Literal[",", ";", "\t"] = ","
    decimal_separator: Literal[".", ","] = "."
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    def snapshot(self, as_of: date) -> dict:
        result = self.model_dump(mode="json")
        if self.published_at > as_of:
            return {**result, "status": "excluded_future_publication"}
        if as_of < date.today() and self.sha256 is None:
            raise DocumentError("Historical market series require a pinned release digest")
        data, source = download(str(self.url), discover_pdf=False)
        digest = hashlib.sha256(data).hexdigest()
        if self.sha256 and digest != self.sha256:
            raise DocumentError("Market series release digest mismatch")
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=self.delimiter)
        if not {self.date_column, self.value_column}.issubset(reader.fieldnames or []):
            raise DocumentError("Market series columns do not match the declared schema")
        points = {}
        for index, row in enumerate(reader, 2):
            raw = (row[self.value_column] or "").strip()
            if raw in {"", ".", "NA", "N/A", ":"}:
                continue
            day = date.fromisoformat(row[self.date_column])
            if day > min(self.published_at, as_of):
                continue
            try:
                value = Decimal(raw.replace(",", ".") if self.decimal_separator == "," else raw)
            except InvalidOperation as exc:
                raise DocumentError(f"Invalid market observation at CSV row {index}") from exc
            if not value.is_finite() or day in points:
                raise DocumentError(f"Non-finite or duplicate market observation at CSV row {index}")
            points[day] = {"observation_date": day, "value": str(value), "source_row": index}
        recent = [points[day] for day in sorted(points)[-2:]]
        delta = Decimal(recent[-1]["value"]) - Decimal(recent[0]["value"]) if len(recent) == 2 else None
        return {
            **result,
            "url": source,
            "sha256": digest,
            "status": "observed" if recent else "unknown",
            "observations": recent,
            "change_in_source_units": delta,
        }
