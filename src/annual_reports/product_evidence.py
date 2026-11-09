"""Propose product facts with addressable catalog, sales-table or narrative spans."""

import re

from .audit import segment_key

BULLET = ("•", "▪")
MARK = re.compile(r"(?:[A-Z][\w-]* )?[\w-]+[®™]")
SALES_TITLE = re.compile(r"^(?:net sales|sales revenue)\b.{0,45}\b(?:segments?|products?)\b", re.I)
UNCERTAIN = re.compile(r"\b(?:planned|proposed|trial|pilot|may be|not (?:yet )?(?:sold|installed|introduced))\b", re.I)


def evidence(page, owner, name, quote, allocation, commercial, kind, *, spans=(), alias=None):
    return {
        "page": page.number,
        "subject_kind": "Segment",
        "subject": owner,
        "relation": "PRODUCES",
        "object_kind": "Product",
        "object": name,
        "quote": quote,
        "allocation_quote": allocation,
        "commercial_quote": commercial,
        "source_spans": list(spans),
        "evidence_rule": kind,
        "alias_evidence": alias,
        "status": "unknown",
        "review": "Awaiting independent evidence review.",
    }


def segment_labels(note):
    labels = {}
    for definition in note["definitions"].values():
        name = definition["name"]
        group = re.search(r"(?:^|•\s*)" + re.escape(name) + r":\s*([^•.]{1,180})", note["context"], re.I)
        terms = re.split(r",| and ", group[1]) if group else []
        for term in [name, *terms]:
            label = segment_key(term)
            if label:
                labels.setdefault(label, set()).add(name)
    return {k: next(iter(v)) for k, v in labels.items() if len(v) == 1}


def sales_rows(page, note):
    """Read row labels only inside explicitly headed product-sales sections."""
    lines = [x.strip() for x in page.relationship_text.splitlines()]
    title = next((line for line in lines if SALES_TITLE.match(line)), "")
    if not title or not any(MARK.search(line) for line in lines):
        return []
    owner, allocation = "", ""
    rows = []
    for line in lines[lines.index(title) + 1 :]:
        definition = note["definitions"].get(segment_key(line).removesuffix(" segment"))
        if definition and line.endswith(":"):
            owner, allocation = definition["name"], line
            continue
        if not owner or not line:
            continue
        label, *values = re.split(r"\s{2,}", line, maxsplit=1)
        if not values:
            owner = ""
            continue
        if segment_key(label).removesuffix(" total") == segment_key(owner):
            owner = ""
            continue
        name = re.sub(r"^(?:Total\s+|[•▪]\s*of which\s+)", "", label, flags=re.I)
        if (
            name.lower().startswith(("other ", "total ", "of which "))
            or set(segment_key(name).split()) <= set(segment_key(owner).split())
            or not re.match(r"^[\w ®™-]+$", name)
            or not re.match(r"^\d[\d,.]*\s", values[0])
            or not any(c in "123456789" for c in values[0].split()[0])
        ):
            continue
        rows.append(evidence(page, owner, name, label, allocation, line, "segmented sales row", spans=[title]))
    return rows


def sales_brand_index(doc, note):
    index = {}
    for page in doc.pages:
        for row in sales_rows(page, note):
            if MARK.fullmatch(row["object"]):
                index.setdefault(segment_key(row["object"]), []).append(
                    {
                        "page": page.number,
                        "quote": row["commercial_quote"],
                        "segment": row["subject"],
                        "allocation_quote": row["allocation_quote"],
                        "sha256": doc.sha256,
                    }
                )
    return index


def paired_device(page, note, cells, i, title):
    """A continuation bullet may explicitly identify what the device is used with."""
    cell = cells[i]
    brand = MARK.match(cell[1:].strip())
    if not brand or "," not in cell or i + 1 >= len(cells):
        return []
    continuation = cells[i + 1]
    if not re.search(r"\b(?:used (?:in|with|for)|for use (?:in|with))\b", continuation, re.I):
        return []
    links = []
    for match in MARK.finditer(cell.split(",", 1)[1]):
        proofs = note.get("sales_brands", {}).get(segment_key(match[0]), [])
        if not proofs:
            return []
        links.extend(proofs)
    owners = {link["segment"] for link in links}
    if len(owners) != 1 or not links:
        return []
    result = evidence(
        page, owners.pop(), brand[0], cell, cell, title, "device for disclosed segment product", spans=[continuation]
    )
    result["cross_page_evidence"] = links
    return [result]


def catalog_rows(page, note, columns, title):
    labels = segment_labels(note)
    rows = []
    for column in columns:
        cells = [re.split(r"\s{2,}", text, maxsplit=1)[0] for text in column.values()]
        owner, allocation = "", ""
        for i, cell in enumerate(cells):
            label = segment_key(cell)
            if label in labels and (cell.isupper() or label in note["definitions"]):
                owner, allocation = labels[label], cell
                continue
            if cell.isupper() and label not in labels and not any(ch.isdigit() for ch in cell):
                owner = ""
            if not owner:
                if cell.startswith(BULLET):
                    rows.extend(paired_device(page, note, cells, i, title))
                continue
            if cell.startswith(BULLET):
                # The first registered brand denotes the family even when the entry lists multiple strengths.
                entry = cell[1:].strip()
                brand = MARK.match(entry)
                if not brand:
                    continue
                name = brand[0]
                qualifier = re.match(r"\s+([a-zA-Z]+),", entry[brand.end() :])
                if qualifier:
                    name += " " + qualifier[1]
                rows.append(evidence(page, owner, name, cell, allocation, title, "catalog item"))
                # A separately trademarked device explicitly co-listed in a catalog entry.
                for accessory in MARK.finditer(entry.split(",", 1)[1] if "," in entry else ""):
                    rows.append(evidence(page, owner, accessory[0], cell, allocation, title, "co-listed catalog item"))
                continue
            if not cell[0].isupper() or cell.startswith("Other ") or MARK.search(cell):
                continue
            # A family heading must introduce at least one bullet; continuation cells retain their own locator.
            parts = [cell]
            if i + 1 < len(cells) and cells[i + 1][:1].islower() and len(cells[i + 1].split()) <= 4:
                parts.append(cells[i + 1])
            following = i + len(parts)
            if following < len(cells) and cells[following].startswith(BULLET):
                rows.append(
                    evidence(
                        page,
                        owner,
                        " ".join(parts),
                        cell,
                        allocation,
                        title,
                        "catalog family heading",
                        spans=[*parts, cells[following]],
                    )
                )
    return rows


def sentence_repairs(page, candidates, note):
    """Repair only an actual introduction or installed model that can be bound to its governing clause."""
    text = " ".join(page.text.split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    rows = []
    for old in candidates:
        if old["status"] != "unknown" or not old.get("allocation_quote") or not old["object"].strip():
            continue
        term = re.escape(old["object"])
        for sentence in sentences:
            hit = re.search(r"(?<!\w)" + term + r"(?!\w)", sentence, re.I)
            if not hit or UNCERTAIN.search(sentence) or len(sentence) > 1400:
                continue
            introduced = re.match(
                r"(?:\s+[\w-]+){0,2},?\s+(?:which\s+)?was (?:commercially )?(?:introduced|launched)\b",
                sentence[hit.end() :],
                re.I,
            )
            installed = re.search(r"\bis installed in\b[^.;:]{0,100}$", sentence[: hit.start()], re.I)
            if not introduced and not installed:
                continue
            rows.append(
                evidence(
                    page,
                    old["subject"],
                    old["object"],
                    sentence,
                    old["allocation_quote"],
                    sentence,
                    "completed commercial clause",
                    alias=old.get("alias_evidence"),
                )
            )
            break
    return rows


def model_scope_rows(page, note):
    """Expand a possessive model enumeration only in the scope of a presently operated service."""
    text = " ".join(page.text.split())
    if not re.search(r"\bScope\b", text):
        return []
    rows = []
    for definition in note["definitions"].values():
        for brand, alias in definition.get("aliases", {}).items():
            pattern = (
                r"(?<!\w)" + re.escape(brand) + r"[\u2019']s (?P<codes>[A-Z0-9-]{1,8}(?:, [A-Z0-9-]{1,8})+"
                r",? and [A-Z0-9-]{1,8}) (?P<family>[a-z]{2,16})s\b"
                r"(?: as well as the (?P<extra>[A-Z][\w-]+) models)?"
            )
            for m in re.finditer(pattern, text, flags=re.I):
                preceding = text[max(0, m.start() - 500) : m.start()]
                service = re.search(r"[^.]{0,150}\bis a [^.]{0,70}\bservice\b[^.]{0,240}\.", preceding, re.I)
                if not service or UNCERTAIN.search(preceding[service.start() :]):
                    continue
                codes = re.split(r",\s*|\s+and\s+", m["codes"].replace(", and ", " and "))
                if not all(code.isupper() or code.isdecimal() for code in codes):
                    continue
                service_line = next(
                    (
                        line
                        for line in page.relationship_text.splitlines()
                        if m[0].split(",")[0] in line and "service" in line.lower()
                    ),
                    "",
                )
                # Preserve the horizontal link from the current service description to the scope cell.
                if not service_line:
                    continue
                scope_x = service_line.index(m[0].split(",")[0])
                if not any(
                    abs(header.index("Scope") - scope_x) <= 3
                    for header in page.relationship_text.splitlines()
                    if "Scope" in header
                ):
                    continue
                names = [code + " " + m["family"] for code in codes]
                if m["extra"]:
                    names.append(m["extra"])
                for name in names:
                    rows.append(
                        evidence(
                            page,
                            definition["name"],
                            name,
                            m[0],
                            m[0],
                            service[0].strip(),
                            "in-service model scope",
                            alias=alias,
                            spans=[service_line.strip()],
                        )
                    )
    return rows


def catalog_family_variants(rows, columns):
    """Group strength/formulation presentations with identical catalog descriptions; keep model codes otherwise."""
    variant_families = {}
    for column in columns:
        presentations = {}
        for cell in column.values():
            m = re.fullmatch(r"[•▪]\s*([\w-]+[®™])\s+(\d+(?:[.,]\d+)?),\s+([^,]+)", cell)
            if m:
                presentations.setdefault((m[1], m[3]), {})[m[2]] = cell
        for (family, _), by_number in presentations.items():
            if len(by_number) >= 2:
                for number in by_number:
                    variant_families[segment_key(family + " " + number)] = (family, by_number)
    for row in rows:
        match = variant_families.get(segment_key(row["object"]))
        if match and row["quote"] in match[1].values():
            row["variant"] = row["object"]
            row["object"] = match[0]
            row["family_presentations"] = list(match[1].values())
