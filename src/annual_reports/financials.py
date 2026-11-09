"""Parse comparable report columns without substituting management KPIs for IFRS results."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from src.annual_reports.documents import Document, Page

NUM = r"[+\u2212\u2013-]?\d+(?:[.,]\d+)*"
PERIOD = r"\d{4}(?:/\d{2,4})?"
TABLE = re.compile(r"^(?P<metric>.+?) (?:nach Segmenten|by segment)s?$", re.I)
HEADER = re.compile(rf"^(?P<unit>Mio\. €|€ million)\s+(?P<a>{PERIOD})\s+(?P<b>{PERIOD})", re.I)
ROW = re.compile(rf"^(.+?)\s+({NUM})\s+({NUM})(?:\s|$)")
GROUP = {"konzern", "group", "group total", "total group"}
BRIDGE = [
    ("Operatives Ergebnis", "Operating result"),
    ("Ergebnis aus Restrukturierung und Sondereinflüssen", "Result from restructuring and special items"),
    ("Ergebnis aus at Equity einbezogenen Unternehmen", "Result from companies consolidated at equity"),
    ("Ergebnis der Betriebstätigkeit", "Result from operations"),
]


def number(raw: str, german: bool) -> Decimal:
    raw = raw.replace("\u2212", "-").replace("\u2013", "-")
    return Decimal(raw.replace(".", "").replace(",", ".") if german else raw.replace(",", ""))


def financial_lines(page: Page) -> list[str]:
    text = page.text.split("[OCR transcription]")[0]
    if page.method == "ocr":
        if "<tr" in text.lower():
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            for row in soup.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
                row.replace_with("\n" + " ".join(cells) + "\n")
            text = soup.get_text()
        text = text.replace("|", " ").replace("<nl>", "\n")
        text = re.sub(r"<(?:fcel|ecel|lcel|ucel|xcel)>", " ", text)
        text = re.sub(r"(?m)^#+ ", "", text)
    return [" ".join(row.split()) for row in text.splitlines() if row.strip()]


def table_id(lines: list[str]) -> str | None:
    return next((line for line in lines if re.fullmatch(r"(?:TABELLE|TABLE) \d+", line, re.I)), None)


def reconciliation(doc: Document) -> list[dict]:
    results = []
    for page in doc.pages:
        lines = financial_lines(page)
        for i, line in enumerate(lines[:-1]):
            match = TABLE.match(line)
            header = HEADER.match(lines[i + 1])
            if not match or not header:
                continue
            german = header["unit"].startswith("Mio")
            rows = []
            for row in lines[i + 2 :]:
                cells = ROW.match(row)
                if not cells:
                    break
                name, *values = cells.groups()
                rows.append({"label": name, "values": [number(v, german) for v in values], "quote": row})
                if name.lower() in GROUP:
                    break
            if len(rows) > 1 and rows[-1]["label"].lower() in GROUP:
                totals = [sum(r["values"][j] for r in rows[:-1]) for j in range(2)]
                results.append(
                    {
                        "metric": match["metric"],
                        "table_id": table_id(lines[i + 2 + len(rows) : i + 4 + len(rows)]),
                        "unit": header["unit"],
                        "periods": [header["a"], header["b"]],
                        "physical_page": page.number,
                        "printed_page": page.printed,
                        "rows": rows,
                        "calculated": totals,
                        "status": "passed" if totals == rows[-1]["values"] else "mismatch",
                    }
                )
        # Scope this bridge to a consolidated table with explicitly labelled units.
        for de, heading, currency in [
            (True, "Geschäftsentwicklung im Konzern", "Mio. €"),
            (False, "Group business performance", "€ million"),
        ]:
            if heading not in lines:
                continue
            start = lines.index(heading)
            block = lines[start : start + 38]
            periods = re.search(rf"({PERIOD})\s+({PERIOD})", "\n".join(block[:4]))
            if not periods:
                continue
            rows = []
            for names in BRIDGE:
                label = names[0 if de else 1]
                m = re.search(
                    rf"^{re.escape(label)}\s+{re.escape(currency)}\s+({NUM})\s+({NUM})", "\n".join(block), re.M
                )
                if m:
                    rows.append({"label": label, "values": [number(v, de) for v in m.groups()], "quote": m[0]})
            if len(rows) == 4:
                totals = [sum(r["values"][j] for r in rows[:3]) for j in range(2)]
                results.append(
                    {
                        "metric": "operating_result_bridge",
                        "table_id": table_id(block),
                        "unit": currency,
                        "periods": list(periods.groups()),
                        "physical_page": page.number,
                        "printed_page": page.printed,
                        "rows": rows,
                        "calculated": totals,
                        "status": "passed" if totals == rows[-1]["values"] else "mismatch",
                    }
                )
    return results


MONTHS = (
    "januar january",
    "februar february",
    "märz march",
    "april",
    "mai may",
    "juni june",
    "juli july",
    "august",
    "september",
    "oktober october",
    "november",
    "dezember december",
)
DATE = r"(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]+)\s+(\d{4})"


def calendar_date(match: re.Match) -> date | None:
    d, month, y = match.groups()
    for i, names in enumerate(MONTHS, 1):
        if month.lower() in names.split():
            return date(int(y), i, int(d))
    return None


def identity(doc: Document) -> dict:
    front = "\n".join(p.text for p in doc.pages[:4])
    dates = list(re.finditer(DATE, front))
    periods = re.search(rf"{DATE}\s+(?:bis|to)\s+{DATE}", front, re.I)
    published = re.search(
        rf"(?:veröffentlicht am|published(?: on)?)\s+{DATE}",
        front + "\n" + "\n".join(p.text for p in doc.pages[-2:]),
        re.I,
    )
    isins = set()
    for page in doc.pages:
        for m in re.finditer(r"\bISIN\s*[: ]*([A-Z]{2}(?:\s?[A-Z0-9]){9}\s?\d)\b", page.text):
            isins.add(m[1].replace(" ", ""))
    parsed_periods = [calendar_date(d) for d in dates if periods and periods.start() <= d.start() < periods.end()]
    return {
        "cover": [line[:160] for line in front.splitlines()[:3]],
        "period_start": parsed_periods[0] if parsed_periods else None,
        "period_end": parsed_periods[-1] if parsed_periods else None,
        "published_at": calendar_date(published) if published else None,
        "isin_candidates": sorted(isins),
        "date_evidence": [m[0] for m in (periods, published) if m],
    }


def comparable_rows(doc: Document) -> list[dict]:
    """Retain identifiable KPIs under explicit comparable-period headers."""
    facts = []
    for page in doc.pages:
        periods = None
        section = ""
        for line in financial_lines(page):
            header = re.fullmatch(rf"(?:Mio\. € |€ million )?({PERIOD})\s+({PERIOD})(?:\s+.*)?", line)
            if header:
                periods = header.groups()
                continue
            if line.startswith(("TABELLE ", "TABLE ")):
                periods = None
            match = re.fullmatch(rf"(.+?)\s+(Mio\. €|€ million|%)\s+({NUM})\s+({NUM})(?:\s+.*)?", line)
            if periods and match:
                label, unit, a, b = match.groups()
                german = unit == "Mio. €" or (
                    unit == "%" and any(w in page.text for w in ("Ergebnis", "Umsatz", "Konzern"))
                )
                facts.append(
                    {
                        "label": label,
                        "unit": unit,
                        "periods": list(periods),
                        "values": [number(a, german), number(b, german)],
                        "physical_page": page.number,
                        "printed_page": page.printed,
                        "section": section,
                        "quote": line,
                    }
                )
            elif not re.search(r"\d", line) and len(line) < 100:
                section = line
    return facts
