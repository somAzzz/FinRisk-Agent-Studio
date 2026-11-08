"""Find the issuer's own consolidated segment note and bind product rows to it."""

import itertools
import re
from collections import Counter

from pydantic import BaseModel, Field

from .audit import audit_segment_edges, segment_key, structured
from .catalog_scope import catalog_bridges, unallocated_mentions
from .product_evidence import (
    catalog_family_variants,
    catalog_rows,
    model_scope_rows,
    sales_brand_index,
    sales_rows,
    sentence_repairs,
)

NOTE_TITLE = re.compile(
    r"(?im)^\s*(?:note\s+)?(?:\d+(?:\.\d+)*[.)]?\s+)?"
    r"(?:segment (?:information|reporting)|segmentberichterstattung|operating segments|reportable segments)\s*$"
)


class Definition(BaseModel):
    name: str
    quote: str


class Definitions(BaseModel):
    segments: list[Definition]


def segment_note(doc):
    """Only a note heading and an explicit definition can authorize a segment."""
    candidates = []
    for page in doc.pages:
        for match in NOTE_TITLE.finditer(page.text):
            content = page.text[match.start() : match.start() + 4000]
            score = len(
                re.findall(
                    r"decision mak|accounting polic|allocated|segments based|"
                    r"segment result|intersegment|internal reporting",
                    content,
                    re.I,
                )
            )
            candidates.append((score, page.number, content))
    definitions = {}
    used = set()
    for _, number, content in sorted(candidates, key=lambda x: (-x[0], x[1])):
        if number in used:
            continue
        used.add(number)
        source = " ".join(content.split())
        result = structured(
            Definitions,
            """Read this candidate financial statement note. Return every explicitly
defined current consolidated reporting segment of the issuer. Copy each name and a short exact quote that
defines it as a segment (the same enumeration can support multiple names). Ignore references to another
note, geographic disclosures, subtotals, comparatives, brands and unallocated operations.
If the extract does not define the reportable segments, return an empty list.""",
            source,
        )
        for item in result.segments:
            quote = " ".join(item.quote.split())
            if not quote or quote not in source or segment_key(item.name) not in segment_key(quote):
                continue
            definitions[segment_key(item.name)] = {
                "name": item.name,
                "quote": quote,
                "page": number,
                "sha256": doc.sha256,
            }
        if definitions:
            # Preserve the adjacent description of each segment's scope for independent row review.
            for definition in definitions.values():
                definition["aliases"] = disclosed_aliases(definition["name"], doc)
            note = {"definitions": definitions, "page": number, "context": source, "sha256": doc.sha256}
            note["sales_brands"] = sales_brand_index(doc, note)
            return note
        if len(used) == 4:
            break
    return {"definitions": {}, "page": None, "context": "", "sha256": doc.sha256}


def disclosed_aliases(name, doc):
    pattern = re.compile(re.escape(name) + r"\s*\(brand name:\s*([^()]{1,80})\)", re.I)
    aliases = {}
    for p in doc.pages:
        for m in pattern.finditer(" ".join(p.text.split())):
            for label in re.split(r"\s+[\u2013\u2014]\s+", m[1]):
                aliases[segment_key(label)] = {"page": p.number, "quote": m[0]}
    return aliases


CATALOG = re.compile(r"\bproduct (?:overview|portfolio|catalog(?:ue)?)(?=\b|[0-9¹²³])", re.I)
TRADE = re.compile(
    r"\b(?:sold|sales|marketed|launched|introduced|series production|started production|"
    r"brand portfolio|market penetration|unit deliveries|units delivered)\b",
    re.I,
)
PROSPECTIVE = re.compile(
    r"\b(?:planned|expected|proposed|trial|phase [123i]+|candidate|regulatory approval"
    r"|will launch|will be|under development)\b",
    re.I,
)


def product_witness(row, indexed, note, catalog):
    """Require a local allocation and an actual commercial disclosure before independent review."""
    segment = segment_key(row["subject"])
    definition = note["definitions"].get(segment)
    if not definition:
        return {}
    labels = {segment, *definition.get("aliases", {})}
    # Some financial notes explicitly enumerate the businesses within a formal segment.
    listed = re.search(re.escape(definition["name"]) + r":\s*([^•.]{1,180})", note["context"], re.I)
    if listed:
        labels.update(segment_key(x) for x in re.split(r",| and ", listed[1]) if x.strip())
    line_id = row["line"]
    before = [(i, line.strip()) for i, line in indexed.items() if i <= line_id]
    for i, text in reversed(before):
        normalized = segment_key(text)
        label = next(
            (
                n
                for n in sorted(labels, key=len, reverse=True)
                if n
                and (
                    normalized in {n, n + " segment"}
                    or (i == line_id and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", normalized))
                )
            ),
            None,
        )
        if label:
            break
        # A subsequent formal section supersedes an earlier heading.
        if normalized.removesuffix(" segment") in note["definitions"]:
            return {}
    else:
        return {}
    local = " ".join(line.strip() for idx, line in indexed.items() if abs(idx - line_id) <= 1)
    table = next(
        (
            line.strip()
            for idx, line in indexed.items()
            if idx <= line_id and re.search(r"\b(net sales|unit sales|sales \(units\)|sales revenue)\b", line, re.I)
        ),
        "",
    )
    if catalog and row["quote"].lstrip().startswith(("•", "▪")):
        commercial = catalog
    elif TRADE.search(local) and not PROSPECTIVE.search(local):
        commercial = local
    elif table and sum(c.isdigit() for c in row["quote"]) >= 4:
        commercial = table
    else:
        return {}
    return {
        "allocation_quote": text,
        "allocation_line": i,
        "commercial_quote": commercial,
        "alias_evidence": definition.get("aliases", {}).get(label),
    }


class ProductRow(BaseModel):
    name: str
    segment: str
    line: int


class ProductRows(BaseModel):
    products: list[ProductRow] = Field(max_length=40)


class RowDecisions(BaseModel):
    supported_indices: list[int]


def product_edges(page, note):
    """Use line IDs so a model never has to reconstruct a quote from separated cells."""
    lines = [line.rstrip() for line in (page.relationship_text or page.text).splitlines() if line.strip()]
    columns = list(bullet_columns(lines)) if page.relationship_method == "layout" else []
    catalog = next((m[0] for line in lines if (m := CATALOG.search(line))), "")
    result = []
    for indexed in columns or [dict(enumerate(lines))]:
        result.extend(_read_lines(indexed, page, note, catalog))
    if columns and catalog:
        catalog_family_variants(result, columns)
    supplemental = sales_rows(page, note) + model_scope_rows(page, note)
    if columns and catalog:
        supplemental.extend(catalog_rows(page, note, columns, catalog))
    supplemental.extend(sentence_repairs(page, result, note))
    known = {(segment_key(r["subject"]), segment_key(r["object"])) for r in result if r["status"] == "supported"}
    proposals = [r for r in supplemental if (segment_key(r["subject"]), segment_key(r["object"])) not in known]
    reviewed = result + review_disclosures(proposals, note)
    if columns and catalog:
        bridges = catalog_bridges(page, note, columns, catalog, reviewed)
        reviewed += review_disclosures(bridges, note, bridges=True)
        reviewed += unallocated_mentions(page, note, columns, catalog, reviewed)
    return reviewed


def review_disclosures(proposals, note, *, bridges=False):
    # Keep each span separate: headings, cells and narrative clauses can have different positions.
    rows = []
    for start in range(0, len(proposals), 12):
        batch = proposals[start : start + 12]
        checks = structured(
            RowDecisions,
            """Independently audit each indexed annual-report product-to-segment fact using its supplied
source spans and the formal segment note. Accept only the exact endpoint or an explicitly named commercial
family (a registered brand shared by listed variants is a family). An issuer's catalog of commercial products
establishes the headed product families and their specifically named entries. A formal note may assign a
catalog business to its formal segment. A positive net-sales row can name a family or one of its members.
A current service's scope can establish that the brand has explicitly enumerated physical model families in
service; it does not establish unit sales. Validate the scope cell's shared noun and brand ownership.
A commercial introduction or actual installation must govern the named product in the cited clause.
Exclude comparators, pilots, future plans, customers' products, geographic areas, broad business totals,
and unsupported assignment of an adjacent column. Return only the supported indices."""
            + (
                """
For catalog bridges, review each complete chain. A named device explicitly listed with a host under an
equipment and business heading needs consistent host sales evidence. A family is marketed within a segment
if at least one directly listed member is independently assigned there, corroborated by the host/member
entry and segmented host sales. This is participation only; do not allocate the siblings or revenue.
For a treatment class, verify that the heading explicitly denotes treatment of the condition quoted in the
formal segment scope. A marked primary entry under that heading shares its scope. Reject merely similar
spelling, inferred indications, or contradictory evidence."""
                if bridges
                else ""
            ),
            {
                "segment_note": note["context"],
                "candidates": [
                    {
                        "index": i,
                        "cross_page_evidence": r.get("cross_page_evidence", []),
                        **{
                            k: r[k]
                            for k in (
                                "subject",
                                "object",
                                "quote",
                                "allocation_quote",
                                "commercial_quote",
                                "source_spans",
                                "evidence_rule",
                                "alias_evidence",
                            )
                        },
                    }
                    for i, r in enumerate(batch)
                ],
            },
        )
        for i, row in enumerate(batch):
            if i in checks.supported_indices:
                row.update(status="supported", review="Local disclosure and formal segment independently verified.")
            else:
                row["review"] = "Independent review did not confirm the structural evidence."
        rows.extend(audit_segment_edges(batch, note))
    return rows


def bullet_columns(lines):
    """Split persistent bullet-list columns at their physical starts, keeping source line IDs."""
    offsets = Counter(m.start() for line in lines for m in re.finditer(r"[•▪]\s", line))
    starts = sorted(x for x, count in offsets.items() if count >= 4)
    if len(starts) < 2 or any(b - a < 12 for a, b in itertools.pairwise(starts)):
        return
    indices = [i for i, line in enumerate(lines) if any(line[x : x + 1] in ("•", "▪") for x in starts)]
    for left, right in zip(starts, [*starts[1:], None], strict=False):
        column = {}
        for i in range(max(0, indices[0] - 5), indices[-1] + 1):
            # A line continuing across the boundary belongs to the preceding column.
            if left and lines[i][left - 1 : left].strip():
                continue
            field = lines[i][left:right]
            if field.startswith("    "):
                continue
            cell = re.split(r"\s{4,}", field.strip(), maxsplit=1)[0]
            if cell:
                column[i] = cell
        if column:
            yield column


def _read_lines(indexed, page, note, catalog):
    result = []
    items = list(indexed.items())
    for start in range(0, len(items), 60):
        block = dict(items[max(0, start - 6) : start + 60])
        context = {
            "segment_note": note["context"],
            "formal_names": [d["name"] for d in note["definitions"].values()],
            "lines": block,
            "issuer_disclosed_brand_names": {
                d["name"]: list(d["aliases"]) for d in note["definitions"].values() if d.get("aliases")
            },
        }
        if catalog:
            context["catalog_heading"] = catalog
        proposed = structured(
            ProductRows,
            """Identify explicitly marketed, named products or product families on
these numbered lines. For each, copy the product spelling (including model or formulation), its line index,
and the exact formal segment from the financial note if directly assigned. A table row under a heading
or a product category explicitly included in the note is evidence. Read columns vertically.
Check narrative launches, existing model lines, named equipment and branded components sold or installed
in commercial products, as well as numeric sales tables. Resolve a brand heading using only supplied
issuer-disclosed brand names. A segment assignment can remain unknown even when the product is clear.
Use unknown for ambiguous assignment. Exclude pipeline projects, ingredients of branded products,
unbranded services, generic activities, vehicle classes and references to another company's products.
Return an empty list if there are no named commercial products.""",
            context,
        )
        rows = []
        for item in proposed.products:
            quote = block.get(item.line, "").strip()
            name = item.name
            if "®" in name or "™" in name:
                name = re.sub(r"(?<=[®™])\d+(?=,|$)", "", name).split(",")[0].strip()
            rows.append(
                {
                    "subject_kind": "Segment",
                    "subject": item.segment,
                    "relation": "PRODUCES",
                    "object_kind": "Product",
                    "object": name,
                    "page": page.number,
                    "quote": quote,
                    "line": item.line,
                    "status": "unknown",
                    "review": "Missing exact product mention, segment definition or independent support.",
                }
            )
        for row in rows:
            row.update(product_witness(row, indexed, note, catalog))
        eligible = [
            i
            for i, r in enumerate(rows)
            if r.get("allocation_quote")
            and segment_key(r["object"])
            and re.search(
                r"(?<!\w)" + re.escape(segment_key(r["object"])) + r"(?!\w)",
                segment_key(re.sub(r"(?<=[®™])\d+(?=,|\s|$)", "", r["quote"])),
            )
        ]
        if eligible:
            checked = structured(
                RowDecisions,
                """Independently verify each indexed segment-to-product proposal.
Accept only an actual named commercial product/family assigned to this exact segment by the product line
and its column, heading or explicit narrative, together with the formal note. The financial note establishes
segment identity but cannot on its own assign a product. Reject nearby unrelated columns, ambiguous
headings, group-only disclosures, projects, services, input components and customer products.
Return only indices whose entire relationship follows from this evidence.""",
                {
                    **context,
                    "candidates": {
                        i: {
                            k: rows[i][k]
                            for k in ("subject", "object", "quote", "line", "allocation_quote", "commercial_quote")
                        }
                        for i in eligible
                    },
                },
            )
            for i in set(checked.supported_indices).intersection(eligible):
                rows[i].update(status="supported", review="Independent page and segment-note review accepted.")
        result.extend(audit_segment_edges(rows, note))
    return result
