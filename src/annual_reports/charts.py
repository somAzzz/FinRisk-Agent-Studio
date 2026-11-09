"""Recover labelled two-series bar charts from PDF text positions and legend swatches."""

import io
import re
from dataclasses import dataclass
from decimal import Decimal
from xml.etree import ElementTree

from PIL import Image

CAPTION = re.compile(r"^(GRAFIK|CHART|FIGURE)(\d+)$", re.I)
NUMBER = r"[+\-\u2013\u2212]?\s*\d+(?:[.,]\d+)*"
VALUE = re.compile(rf"({NUMBER})\s+([^\d%]+)")
RATE = re.compile(rf"({NUMBER})\s*%")
YEAR = re.compile(r"(?:19|20)\d{2}")


@dataclass
class Line:
    text: str
    x: float
    y: float
    right: float
    height: float


def chart_caption(text: str):
    return CAPTION.fullmatch("".join(text.split()))


def dominant_color(image, box):
    region = image.crop(box)
    size = region.width * region.height
    for frequency, color in sorted(region.getcolors(maxcolors=max(1, size)) or [], reverse=True):
        if max(color) - min(color) > 20 and frequency >= size / 5:
            return color
    return None


def decimal_string(raw: str, german: bool) -> str:
    raw = "".join(raw.split()).translate({0x2013: "-", 0x2212: "-"})
    return str(Decimal(raw.replace(".", "").replace(",", ".") if german else raw.replace(",", "")))


def chart_rows(layout: bytes, png: bytes, physical_page: int, printed_page: str | None) -> list[dict]:
    page = ElementTree.fromstring(layout).find(".//{*}page")
    if page is None:
        return []
    lines = []
    for el in page.findall(".//{*}line"):
        x, y, right, bottom = (float(el.attrib[key]) for key in ("xMin", "yMin", "xMax", "yMax"))
        lines.append(Line(" ".join(w.text or "" for w in el.findall("{*}word")), x, y, right, bottom - y))
    with Image.open(io.BytesIO(png)) as source:
        image = source.convert("RGB")
    sx, sy = image.width / float(page.attrib["width"]), image.height / float(page.attrib["height"])

    def color(left, right, line):
        middle = line.y + line.height / 2
        return dominant_color(
            image,
            (
                round(left * sx),
                round((middle - line.height / 5) * sy),
                round(right * sx),
                round((middle + line.height / 5) * sy),
            ),
        )

    result = []
    for caption in lines:
        match = chart_caption(caption.text)
        if not match:
            continue
        h = caption.height
        years = [
            line
            for line in lines
            if YEAR.fullmatch(line.text)
            and 0 < caption.y - line.y < 4 * h
            and caption.right - 15 * h < line.x < caption.right + h
        ]
        if len(years) != 2 or years[0].text == years[1].text:
            continue
        legend = {color(line.x - line.height, line.x - 1, line): line.text for line in years}
        if len(legend) != 2 or None in legend:
            continue
        rates = sorted(
            (
                line
                for line in lines
                if RATE.fullmatch(line.text)
                and line.y < min(y.y for y in years)
                and abs(line.x - min(y.x for y in years)) < h
            ),
            key=lambda line: -line.y,
        )
        last_y = min(y.y for y in years)
        for rate in rates:
            if last_y - rate.y > 7 * h:
                break
            cells = [
                line
                for line in lines
                if VALUE.fullmatch(line.text) and line.right < rate.x and rate.y - h / 2 < line.y < rate.y + 2 * h
            ]
            if len(cells) != 2 or abs(cells[0].x - cells[1].x) > h:
                break
            labels = [
                line
                for line in lines
                if abs(line.x - cells[0].x) < h and 0 < rate.y - line.y < 2 * h and re.match(r"[^\W\d_]", line.text)
            ]
            if len(labels) != 1:
                break
            values = {}
            units = set()
            for cell in cells:
                year = legend.get(color(cell.x, cell.right, cell))
                value, unit = VALUE.fullmatch(cell.text).groups()
                units.add(unit)
                values[year] = value.strip()
            if None in values or len(values) != 2 or len(units) != 1:
                break
            prior, current = sorted(values)
            german = match[1].upper() == "GRAFIK"
            published_change = "".join(RATE.fullmatch(rate.text)[1].split()).translate({0x2013: "-", 0x2212: "-"})
            normalized = {year: decimal_string(value, german) for year, value in values.items()}
            change_number = decimal_string(published_change, german)
            # Rounded chart labels can imply a different percentage, but a reversed direction is suspect.
            direction = Decimal(normalized[current]) - Decimal(normalized[prior])
            if Decimal(normalized[prior]) > 0 and direction * Decimal(change_number) < 0:
                break
            result.append(
                {
                    "chart_id": f"{match[1].upper()} {match[2]}",
                    "metric": labels[0].text,
                    "values": {current: values[current], prior: values[prior]},
                    "unit": units.pop(),
                    "decimal_values": normalized,
                    "change": {
                        "from_year": prior,
                        "to_year": current,
                        "unit": "%",
                        "value": published_change,
                        "decimal_value": change_number,
                    },
                    "physical_page": physical_page,
                    "printed_page": printed_page,
                    "method": "pdf_coordinates_and_legend_color",
                }
            )
            last_y = rate.y
    return list(reversed(result))


def chart_text(rows: list[dict]) -> str:
    """Render each chart with a single legend and its published change column."""
    groups = {}
    for row in rows:
        groups.setdefault(row["chart_id"], []).append(row)
    blocks = []
    for caption, group in groups.items():
        current, prior = group[0]["values"]
        blocks.append(f"{caption}\nMetric | {current} | {prior} | Change (%)")
        for row in group:
            blocks.append(
                f"{row['metric']} | {row['values'][current]} {row['unit']} | "
                f"{row['values'][prior]} {row['unit']} | {row['change']['value']} %"
            )
    return "\n".join(blocks)
