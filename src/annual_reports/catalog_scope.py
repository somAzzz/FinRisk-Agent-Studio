"""Evidence bridges for commercial catalog groups; never carry ownership across columns."""

import re

from .audit import segment_key
from .product_evidence import BULLET, MARK, evidence, segment_labels

EQUIPMENT = re.compile(r"\b(?:systems|devices|equipment|accessories)\b$", re.I)
NAMED_DEVICE = re.compile(r"([A-Z][\w-]*(?: [A-Z][\w-]*){0,5} (?:Device|Adapter|Applicator|Injector|Cartridge))")
THERAPY = re.compile(r"\banti-?([a-z]+)\s+(?:agents|treatments|therapies|medications)\b$", re.I)


def groups(columns, note):
    labels = segment_labels(note)
    for column in columns:
        cells = [re.split(r"\s{2,}", cell, maxsplit=1)[0] for cell in column.values()]
        owner, section = None, ""
        for i, heading in enumerate(cells[:-1]):
            if segment_key(heading) in note["definitions"] or (heading.isupper() and not re.search(r"\d", heading)):
                owner, section = labels.get(segment_key(heading)), heading
            if heading.startswith(BULLET) or MARK.search(heading) or not cells[i + 1].startswith(BULLET):
                continue
            if not (EQUIPMENT.search(heading) or THERAPY.search(heading)):
                continue
            entries = []
            for cell in cells[i + 1 :]:
                if cell.startswith(BULLET):
                    entries.append([cell])
                else:
                    # Keep an unmistakable wrapped trademark in its own entry. Never
                    # walk past a non-bullet into another run of products.
                    if entries[-1][-1].endswith((" and", ",")) and MARK.fullmatch(cell):
                        entries[-1].append(cell)
                    break
            yield owner, section, heading, entries


def condition_proof(heading, note):
    """A narrowly generated grammatical match is only a proposal for the independent judge."""
    match = THERAPY.search(heading)
    if not match:
        return None

    def stem(word):
        return re.sub(r"(?:ic|es)$", "", word.casefold())

    target = stem(match[1])
    if len(target) < 5:
        return None
    hits = []
    for definition in note["definitions"].values():
        name = definition["name"]
        scope = re.search(r"(?:^|•\s*)(" + re.escape(name) + r":\s*([^•.]{1,180})(?=[•.]|$))", note["context"], re.I)
        if not scope:
            continue
        for raw_term in re.split(r",| and ", scope[2]):
            term = raw_term.strip()
            if stem(term) == target:
                hits.append(
                    {
                        "segment": name,
                        "page": note["page"],
                        "sha256": note["sha256"],
                        "quote": scope[1].strip(),
                        "allocation_quote": term,
                    }
                )
    return hits[0] if len(hits) == 1 else None


def catalog_bridges(page, note, columns, title, verified):
    rows = []
    sales = note.get("sales_brands", {})

    def anchored(name, owner):
        proofs = sales.get(segment_key(name), [])
        return proofs if {p["segment"] for p in proofs} == {owner} else []

    for owner, section, heading, entries in groups(columns, note):
        marked = []
        for entry in entries:
            first = MARK.match(entry[0][1:].strip())
            if first:
                marked.append((first[0], entry))
        if not marked:
            continue
        condition = condition_proof(heading, note)
        if condition and (not owner or owner == condition["segment"]):
            # A therapy class is a scope witness; a sibling family anchor never is.
            for name, entry in [(heading, marked[0][1]), *marked]:
                row = evidence(
                    page,
                    condition["segment"],
                    name,
                    heading if name == heading else entry[0],
                    heading,
                    title,
                    "treatment class within disclosed condition",
                    spans=entry,
                )
                row["cross_page_evidence"] = [condition]
                rows.append(row)
        if not EQUIPMENT.search(heading) or heading.lower().startswith("other "):
            continue
        for host, entry in marked:
            parts = entry[0][1:].strip().split(",", 1)
            if len(parts) != 2 or parts[0] != host:
                continue
            if owner and (proof := anchored(host, owner)):
                item = NAMED_DEVICE.fullmatch(re.split(r"\s+and(?:\s|$)|,", parts[1].strip(), maxsplit=1)[0])
                if item:
                    row = evidence(
                        page,
                        owner,
                        item[1],
                        entry[0],
                        section,
                        title,
                        "named equipment in commercially allocated host entry",
                        spans=[heading, *entry],
                    )
                    row["cross_page_evidence"] = proof
                    rows.append(row)
            if owner:
                continue
            # Family participation only: an independently allocated member, a primary listing
            # of that member here, AND a separate host/member pair in this very group.
            member = parts[1].strip()
            primary = next((item for name, item in marked if name == member and item != entry), None)
            if not primary or not MARK.fullmatch(member):
                continue
            direct = [
                r
                for r in verified
                if r["status"] == "supported"
                and r["object"] == member
                and r.get("evidence_rule") == "co-listed catalog item"
                and r["quote"] != entry[0]
            ]
            owners = {r["subject"] for r in direct}
            if len(owners) != 1 or not (proof := anchored(host, next(iter(owners)))):
                continue
            witness = direct[0]
            row = evidence(
                page,
                witness["subject"],
                heading,
                heading,
                heading,
                title,
                "catalog family with independently allocated member",
                spans=[*primary, *entry, witness["allocation_quote"], witness["quote"]],
            )
            row["cross_page_evidence"] = proof
            row["scope_limit"] = "Family participation only; no allocation of other members or amounts."
            rows.append(row)
    return rows


def unallocated_mentions(page, note, columns, title, reviewed):
    """Retain commercial names from unlabelled columns without inventing a segment endpoint."""
    known = {segment_key(row["object"]) for row in reviewed if row["status"] == "supported"}
    rows = []
    labels = segment_labels(note)
    leading_name = re.compile(r"(?:[A-Z][\w-]* )*[\w-]+[®™](?: (?:[A-Z][\w®™-]*|\d+))*")
    for column in columns:
        cells = [re.split(r"\s{2,}", cell, maxsplit=1)[0] for cell in column.values()]
        # Only whole continuation columns: mixed/unrecognised section boundaries are not a
        # basis for this pass. An explicit candidate is a mention, not a graph traversal edge.
        if any(segment_key(cell) in labels for cell in cells):
            continue
        heading = ""
        for i, cell in enumerate(cells):
            if cell.startswith(BULLET):
                m = leading_name.match(cell[1:].strip().split(",", 1)[0])
                name = m[0] if m and heading else ""
            elif i and cells[i - 1].startswith(BULLET) and re.fullmatch(r"[\w-]+[®™]\)", cell):
                name = cell[:-1] if heading else ""
            elif i + 1 < len(cells) and cells[i + 1].startswith(BULLET) and cell[0].isupper() and not MARK.search(cell):
                heading = cell
                name = "" if heading.lower().startswith("other ") else heading
            else:
                continue
            if name and segment_key(name) not in known:
                rows.append(
                    {
                        "page": page.number,
                        "subject_kind": "Segment",
                        "subject": "unknown",
                        "relation": "PRODUCES",
                        "object_kind": "Product",
                        "object": name,
                        "quote": cell,
                        "commercial_quote": title,
                        "source_spans": [heading],
                        "status": "unknown",
                        "evidence_rule": "unallocated catalog mention",
                        "review": "Commercial catalog mention only; no verified formal segment allocation.",
                    }
                )
    return rows
