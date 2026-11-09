"""Conservative issuer resolution. An instrument, a brand or an unqualified symbol is not an issuer."""

import hashlib
import re
import unicodedata

from src.annual_reports.financials import NUM, number


def words(text):
    return " ".join(text.casefold().split())


def extract_issuer(doc, cover):
    name = (cover or [""])[0]
    ids = {}
    listings = []
    for page in doc.pages:
        text = page.text.split("[OCR transcription]")[0]
        # Require the cover issuer to be the grammatical subject of its own domicile note.
        if not name:
            continue
        anchored = re.compile(
            r"^Die " + re.escape(name) + r" hat ihren Sitz\b[^;]{0,160};[^.;]{0,260}"
            r"Handelsregister unter (HR[AB])(?:-Nr\.)?\s*(\d+) beim\s+"
            r"Amtsgericht ([\wÄÖÜäöüß -]+?) eingetragen",
            re.I | re.M,
        )
        for match in anchored.finditer(text):
            court = unicodedata.normalize("NFC", words(match[3])).replace(" ", "-")
            key = f"de-{court}-{match[1].lower()}-{int(match[2])}"
            ids[key] = {"page": page.number, "quote": " ".join(match[0].split())}
        # Only the issuer's *share* table. Exclude third-party instruments and adjacent bond tables.
        for m in re.finditer(r"(?im)^Börsendaten der ([^\n]+?)-Aktie\s*\nISIN\s+([A-Z0-9 ]+)$", text):
            if words(name) not in {words(m[1]), words(m[1] + " AG")}:
                continue
            block = re.split(r"\n(?:TABELLE |Anleihen |Bonds )", text[m.start() : m.end() + 600], maxsplit=1)[0]
            symbol = re.search(r"(?m)^Börsenkürzel\s+([A-Z0-9.-]+)$", block)
            if symbol:
                qualified = re.search(r"Tickersymbol Reuters\s+([A-Z0-9]+\.[A-Z]+)\s+\(", block)
                listings.append(
                    {
                        "symbol": symbol[1],
                        "qualified": qualified[1] if qualified else None,
                        "isin": m[2].replace(" ", ""),
                        "page": page.number,
                        "quote": block,
                    }
                )
    # An ESEF filing can identify its reporting entity without a German registration note.
    # Do not use arbitrary identifiers mentioned in the narrative or a minority of contexts.
    if doc.tagged_facts:
        entities = {tuple(f.get("reporting_entity") or ()) for f in doc.tagged_facts}
        if len(entities) == 1 and len(entity := next(iter(entities))) == 2:
            scheme, value = entity
            if scheme in {"http://standards.iso.org/iso/17442", "https://standards.iso.org/iso/17442"} and re.fullmatch(
                r"[A-Z0-9]{18}[0-9]{2}", value
            ):
                digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
                if int(digits) % 97 == 1:
                    ids["lei-" + value.lower()] = {
                        "page": 1,
                        "quote": "XBRL reporting entity: " + value + " · " + scheme,
                    }
    if len(ids) != 1:
        return {
            "status": "unknown",
            "company_id": None,
            "reason": "No unique self-disclosed registration",
            "listings": [],
        }
    key, proof = next(iter(ids.items()))
    return {"status": "confirmed", "company_id": key, "name": name, "registration": proof, "listings": listings}


def range_questions(doc, meta):
    """Freeze narrow metric contracts from an outlook; do not infer a target year from the later filing."""
    result = []
    for p in doc.pages:
        text = p.text.split("[OCR transcription]")[0]
        if "Prognosebericht" not in text:
            continue
        for m in re.finditer(
            r"Das operative Ergebnis im Segment ([^\n.]+?) erwarten wir in einer\s+"
            rf"Bandbreite zwischen ({NUM}) und ({NUM}) (Mio\. €)",
            text,
        ):
            seg = m[1]
            # Require an explicit fiscal year on the page (not a sugar marketing year).
            years = set(re.findall(r"Geschäftsjahr(?:es|s)?\s+(\d{4}/\d{2})", text))
            if not meta["period_end"]:
                continue
            end = int(str(meta["period_end"])[:4])
            year = f"{end}/{str(end + 1)[-2:]}"
            if year not in years:
                continue
            key = hashlib.sha256(f"{doc.sha256}:{p.number}:{m[0]}".encode()).hexdigest()[:24]
            result.append(
                {
                    "id": key,
                    "question": f"Did {seg} report an operating result inside the disclosed {year} range?",
                    "segment": seg,
                    "metric": "Operatives Ergebnis",
                    "unit": m[4],
                    "period": year,
                    "page": p.number,
                    "range": sorted([float(number(v, True)) for v in m.group(2, 3)]),
                    "quote": " ".join(m[0].split()),
                }
            )
    return result
