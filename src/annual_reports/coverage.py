"""Paired page-coverage experiment. Both arms reuse identical page-level decisions."""

import re

from .audit import structured
from .blind import Extraction, adjudicate, plain, sample


def eight_pages(doc):
    ranked = list(sample(doc))
    rest = sorted(doc.pages, key=lambda p: -len(re.findall(r"segment|customer|supplier|product|facilit", p.text, re.I)))
    return list(dict.fromkeys([*ranked, *(p.number for p in rest if p.text.strip())]))[:8]


def windows(text, width=5600, overlap=600):
    for start in range(0, len(text), width - overlap):
        yield text[start : start + width]
        if start + width >= len(text):
            break


def page_edges(cover, number, text, *, segment_note=None):
    rows = []
    for window in windows(text):
        result = structured(
            Extraction,
            """Extract all explicitly disclosed operating relationships on this page within
this evaluation scope: issuer HAS_SEGMENT formally named reporting segment; named reporting segment PRODUCES
named commercial product or product family, USES named input, OPERATES named facility, SOURCES_FROM named supplier,
SERVES named customer or customer class, or LOCATED_IN named operating region. Split distinct endpoints.
Use the disclosed segment name, not an inferred segment based on your industry knowledge. We allow a page heading
or financial segment table to identify the segment. Exclude consolidated group product lists without segment
assignment, affiliates, proposed operations and countries that are only sales destinations. Match the relation's
meaning, including marketed products under PRODUCES; the role does not imply physical manufacture.
Copy a short contiguous verbatim passage and the physical page number. Return no edges when this page is silent.
Use company name on cover as issuer. Do not infer missing relationships.""",
            {"cover": cover, "page": number, "text": window, "formal_segment_note": segment_note or {}},
        )
        source = plain(window)
        valid, contexts = [], []
        for e in result.edges:
            row = e.model_dump()
            valid_type = (
                e.subject_kind == "Company" and e.relation == "HAS_SEGMENT" and e.object_kind == "Segment"
            ) or (e.subject_kind == "Segment" and e.relation != "HAS_SEGMENT")
            span = plain(e.quote)
            if not valid_type:
                continue
            if e.page != number or not span or span not in source:
                rows.append({**row, "status": "unknown", "review": "Missing verbatim evidence on cited page"})
                continue
            pos = source.index(span)
            valid.append(row)
            contexts.append(source[max(0, pos - 850) : pos + len(span) + 350])
        rows.extend(
            adjudicate(
                valid,
                contexts,
                "Audit the directional edge and types. Require both the named "
                "reporting segment and its object to be bound by this passage, its heading or column. A product "
                "sold by the issuer alone does not identify a reporting segment. A therapeutic area or brand is "
                "not automatically a reporting segment. Allow a marketed product under PRODUCES.",
                shared_evidence={"page": window, "formal_segment_note": segment_note or {}},
            )
        )
    return rows


def collapse(rows):
    result = {}
    for row in rows:
        ident = tuple(
            plain(row[k]).casefold() for k in ("subject_kind", "subject", "relation", "object_kind", "object")
        )
        if ident not in result or (result[ident]["status"] == "unknown" and row["status"] == "supported"):
            result[ident] = row
    return list(result.values())
