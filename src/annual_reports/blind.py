"""Single-report exposure discovery. No case manifest, aliases, or issuer-specific rules."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .audit import key, structured
from .blind_sources import digest, discover
from .documents import MAX_BYTES, download, extract

Kind = Literal["Company", "Segment", "Product", "Facility", "Region", "Supplier", "Customer", "Customer class"]
Role = Literal["HAS_SEGMENT", "PRODUCES", "USES", "OPERATES", "SOURCES_FROM", "SERVES", "LOCATED_IN"]


class Edge(BaseModel):
    subject: str
    subject_kind: Kind
    relation: Role
    object: str
    object_kind: Kind
    page: int
    quote: str


class Extraction(BaseModel):
    issuer: str
    edges: list[Edge] = Field(max_length=15)


class Review(BaseModel):
    index: int
    supported: bool
    reason: str


class Reviews(BaseModel):
    decisions: list[Review]


class Task(BaseModel):
    target: str
    question: str
    web_query: str
    us_regulatory_relevance: bool
    registry_term: str


class Tasks(BaseModel):
    tasks: list[Task] = Field(max_length=3)


class Event(BaseModel):
    target: str
    page: int
    quote: str


class Events(BaseModel):
    items: list[Event] = Field(max_length=1)


def plain(text):
    return " ".join(text.split())


def sample(doc):
    # Rank the whole document, separately for segment definitions and operating relationships.
    groups = [
        r"reportable segments|operating segments|business segments|organized into|principal products|this segment",
        r"production facilit|manufactur(?:es|ing)|key suppliers|major customers|principal customers|supply chain",
        r"business overview|business description|our products|business units|segment develops|segment provides",
    ]
    pages = {p.number: p.text for p in doc.pages if len(p.text.strip()) > 60}
    result = {}
    for pattern in groups:
        ranked = sorted(pages, key=lambda k: -len(re.findall(pattern, pages[k], re.I)))
        for number in ranked[:3]:
            hits = list(re.finditer(pattern, pages[number], re.I))
            if hits:
                start = max(0, hits[0].start() - 800)
                result[number] = plain(pages[number][start : start + 6500])
    if not result:
        result = {n: plain(t[:3500]) for n, t in list(pages.items())[:8]}
    return result


def adjudicate(rows, context, prompt, *, shared_evidence=None):
    if not rows:
        return []
    claims = [{"index": i, "claim": row, "source": context[i]} for i, row in enumerate(rows)]
    response = structured(
        Reviews,
        prompt + " Reject ambiguous pronouns without a referent, co-occurrence, "
        "implied corporate ownership, geographic proximity, and scope or direction mismatches. "
        "Return one verdict for every supplied index, using only the supplied original text.",
        {"claims": claims, "shared_evidence": shared_evidence} if shared_evidence else claims,
    )
    decisions = {}
    for d in response.decisions:
        if d.index in decisions or not 0 <= d.index < len(rows):
            raise ValueError("Invalid independent review index")
        decisions[d.index] = d
    return [
        {
            **r,
            "status": "supported" if i in decisions and decisions[i].supported else "unknown",
            "review": decisions[i].reason if i in decisions else "Missing independent review",
        }
        for i, r in enumerate(rows)
    ]


def extract_edges(doc):
    selected = sample(doc)
    result = structured(
        Extraction,
        """Extract a compact graph from this annual report. Use its legal issuer and
actual named reporting segments. First record issuer HAS_SEGMENT segment. Then prioritize segment PRODUCES
named product/model/family or OPERATES facility, USES input, SERVES customer/class, SOURCES_FROM supplier.
Use exact segment names consistently. Include several distinct products by their precise disclosed names.
For jointly offered products do not assume exclusivity. For each edge copy a contiguous verbatim quote
and its physical page, including section heading or referent when needed. Never fill gaps with prior knowledge.
Prefer material, traceable edges across segments. Separate a named customer from an industry class.""",
        {"cover": doc.pages[0].text[:1500], "pages": selected},
    )
    verified, invalid, contexts, seen = [], [], [], set()
    for proposal in result.edges:
        row = proposal.model_dump()
        page = selected.get(proposal.page, "")
        fingerprint = tuple(row[k] for k in ("subject_kind", "subject", "relation", "object_kind", "object"))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        if not plain(proposal.quote) or plain(proposal.quote) not in page or proposal.subject == proposal.object:
            invalid.append({**row, "status": "unknown", "review": "Missing verbatim citation or invalid endpoints"})
            continue
        verified.append(row)
        start = page.index(plain(proposal.quote))
        contexts.append(page[max(0, start - 700) : start + len(plain(proposal.quote)) + 180])
    audited = adjudicate(
        verified,
        contexts,
        "Audit each typed, directed annual-report edge. A nearby heading may "
        "resolve a segment only when the quoted clause clearly belongs to its section. Check the "
        "exact product, segment, party and role. Reject unsupported precision.",
    )
    from .audit import audit_segment_edges
    from .coverage import collapse
    from .segments import product_edges, segment_note

    note = segment_note(doc)
    checked = audit_segment_edges(audited + invalid, note)
    for definition in note["definitions"].values():
        checked.append(
            {
                "subject_kind": "Company",
                "subject": result.issuer,
                "relation": "HAS_SEGMENT",
                "object_kind": "Segment",
                "object": definition["name"],
                "page": definition["page"],
                "quote": definition["quote"],
                "segment_evidence": definition,
                "status": "supported",
                "review": "Explicitly defined in the consolidated segment note.",
            }
        )
    for row in checked:
        if row["relation"] == "PRODUCES" and row["object_kind"] == "Product":
            row.update(status="unknown", review="Requires a verified product row and commercial disclosure.")
    for page in doc.pages:
        checked.extend(product_edges(page, note))
    return result.issuer, [p.number for p in doc.pages], collapse(checked)


def entity(kind, name):
    return kind + "/" + name


def routes(rows):
    # A corporate parent or shared geography cannot transfer exposure to every reporting segment.
    segments = {
        r["object"]
        for r in rows
        if r["status"] == "supported"
        and r["subject_kind"] == "Company"
        and r["relation"] == "HAS_SEGMENT"
        and r["object_kind"] == "Segment"
    }
    output = {}
    for r in rows:
        if (
            r["status"] == "supported"
            and r["subject_kind"] == "Segment"
            and r["subject"] in segments
            and r["relation"] in {"PRODUCES", "USES", "OPERATES", "SOURCES_FROM", "SERVES"}
            and r["object_kind"] not in {"Company", "Segment", "Region", "Customer class"}
        ):
            output.setdefault(entity(r["object_kind"], r["object"]), []).append(r)
    return output


def investigate(issuer, paths, cutoff, folder, *, discovery=discover):
    if not paths:
        return [], [], [], []
    plan = structured(
        Tasks,
        """Choose up to three material, distinct targets from the supplied graph. Copy target IDs.
Prefer named products or facilities that can be identified unambiguously in an independent primary publication.
Ask about external developments affecting those targets. Generate ordinary web search queries and, when a US
official regulatory record is relevant, a short registry search term (issuer common name plus product identifier).
Do not guess an event, title, URL, publication, financial effect, or counterparty. Use no prior company knowledge.""",
        {"issuer": issuer, "target_ids": list(paths)},
    )
    tasks = [t.model_dump() for t in plan.tasks if t.target in paths and "://" not in t.web_query + t.registry_term]
    # Start official catalogue searches at the granularity disclosed in the annual report.
    # A model-generated variant name could silently exclude the other members of a family.
    issuer_terms = re.sub(r"\b(the|company|inc|plc|ltd|corporation|ag|sa)\b", "", issuer, flags=re.I)
    for task in tasks:
        if task["us_regulatory_relevance"]:
            task["registry_term"] = plain(issuer_terms + " " + task["target"].split("/", 1)[1])
    docs, trace = discovery(tasks, cutoff, folder)
    events, unknowns = [], []
    for doc in docs:
        # Always require an entity-specific passage in the original document, not a match to the issuer alone.
        windows = []
        for target in paths:
            name = target.split("/", 1)[1]
            tokens = [w for w in re.findall(r"[\w-]+", name) if any(c.isdigit() for c in w)]
            needles = [name, *tokens] if tokens else [name]
            for number, text in enumerate(doc["pages"], 1):
                for needle in needles:
                    m = re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", text, re.I)
                    if m:
                        windows.append(
                            {"target": target, "page": number, "text": text[max(0, m.start() - 550) : m.end() + 1250]}
                        )
                        break
                if len(windows) >= 6:
                    break
            if len(windows) >= 6:
                break
        if not windows:
            unknowns.append(
                {"source": doc["url"], "status": "unknown", "reason": "No identified graph target in original"}
            )
            continue
        proposal = structured(
            Events,
            """Select at most one contiguous self-contained passage that states a concrete regulatory or operational
development from this specific document about a listed target. Copy target ID and the decisive verbatim quote
containing the entity, action and scope. Be precise about
affected variants, operator obligations and proposed versus final action. The target can be a family only when
the source explicitly identifies a member of that family; keep the claim restricted to the identified variant.
Check document title and identifier so adjacent articles on a printed page cannot be used. No inference
about sales, deliveries, manufacturer obligations or financial damage. Return an empty list if unclear.""",
            {"issuer": issuer, "title": doc["title"], "targets_and_excerpts": windows},
        )
        accepted = False
        for e in proposal.items:
            window = next(
                (
                    w
                    for w in windows
                    if (w["target"], w["page"]) == (e.target, e.page) and plain(e.quote) and plain(e.quote) in w["text"]
                ),
                None,
            )
            if not window:
                continue
            row = adjudicate(
                [e.model_dump()],
                ["Issuer to verify: " + issuer + "\nPublished title: " + doc["title"] + "\nDecisive span: " + e.quote],
                "Confirm that the decisive span establishes a concrete development for this issuer/product "
                "or counterparty. "
                "Reject a generic match or a fragment that gives only a product identifier. Verify the action in the "
                "document. Reject a rule about another product, a proposal reported as final, or a "
                "financial/operational effect merely inferred from a regulator's action.",
            )[0]
            if row["status"] == "supported":
                events.append(
                    {
                        **row,
                        "fact": e.quote,
                        "source": doc["url"],
                        "published": doc["published"],
                        "digest": doc["digest"],
                        "title": doc["title"],
                        "segments": sorted({r["subject"] for r in paths[e.target]}),
                        "realized_impact": "unknown",
                        "attributable_amount": "unknown",
                        "fulfillment": "unknown",
                    }
                )
                accepted = True
        if not accepted:
            unknowns.append({"source": doc["url"], "status": "unknown", "reason": "No audited target-specific event"})
    return tasks, trace, events, unknowns


def report_md(r):
    rows = r["edges"]
    lines = [
        f"# {r['issuer']} · single-report exposure review",
        "",
        f"Observation date {r['as_of']}. "
        f"The only company-specific input was the annual report (SHA-256 `{r['seed_sha256']}`). "
        f"The reader screened {r['page_count']} PDF pages and selected {len(r['sample_pages'])} for extraction.",
        "",
        "## External events and segment exposure",
        "",
    ]
    for e in r["events"]:
        lines.extend(
            [
                f"- **{', '.join(e['segments'])}** via {e['target']}. {e['fact']} "
                f"Actual financial impact, attributable amount and fulfillment are unknown. "
                f"[Primary publication, {e['published']}, PDF page or HTML section {e['page']}]({e['source']})"
            ]
        )
    if not r["events"]:
        lines.append("No external event passed both the primary-source and segment-path checks.")
    lines.extend(
        [
            "",
            "## Annual-report graph",
            "",
            "| Subject | Relation | Object | Evidence status | PDF page |",
            "|---|---|---|---|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['subject']} | {row['relation']} | {row['object']} | "
            f"{'Issuer disclosure' if row['status'] == 'supported' else 'unknown'} | {row['page']} |"
        )
    lines.extend(["", "## Tracking questions", ""])
    for t in r["tasks"]:
        covered = any(e["target"] == t["target"] for e in r["events"])
        lines.append(f"- {t['question']} **{'External event located' if covered else 'unknown'}**")
    lines.extend(
        [
            "",
            "The companion JSON preserves quotations, review decisions, search queries, rejected candidates "
            "and graph verification. A regulatory development can establish product exposure while its realized "
            "financial effect remains unknown.",
        ]
    )
    return "\n".join(lines) + "\n"


def project(graph, result):
    scope = key("blind-exposure-v1", result)
    edges = []

    def add(a, role, b, basis, source, page, quote, note=None):
        edges.append(
            {
                "a": a,
                "b": b,
                "role": role,
                "basis": basis,
                "digest": source,
                "page": page,
                "quote": quote,
                "note_page": note.get("page") if note else None,
                "note_quote": note.get("quote") if note else None,
            }
        )

    for r in result["edges"]:
        if r["status"] == "supported":
            add(
                entity(r["subject_kind"], r["subject"]),
                r["relation"],
                entity(r["object_kind"], r["object"]),
                "annual_report_disclosure",
                result["seed_sha256"],
                r["page"],
                r["quote"],
                r.get("segment_evidence"),
            )
    for e in result["events"]:
        add(
            entity("Event", key(e["digest"], e["target"], e["fact"])),
            "CONCERNS",
            e["target"],
            "external_confirmation",
            e["digest"],
            e["page"],
            e["quote"],
        )
    graph.run(
        "CREATE CONSTRAINT annual_exposure_id IF NOT EXISTS FOR (n:AnnualExposure) REQUIRE (n.scope,n.id) IS UNIQUE"
    )

    def write(run):
        params = {"scope": scope, "edges": edges}
        run(
            """UNWIND $edges AS x MERGE (a:AnnualExposure {scope:$scope,id:x.a})
               MERGE (b:AnnualExposure {scope:$scope,id:x.b})
               SET a.kind=split(x.a,'/')[0], b.kind=split(x.b,'/')[0]
               MERGE (a)-[r:EXPOSURE {role:x.role,digest:x.digest,page:x.page,quote:x.quote}]->(b)
               SET r.provenance=x.basis, r.segment_note_page=x.note_page, r.segment_note_quote=x.note_quote""",
            params,
        )
        read = run(
            """MATCH (e:AnnualExposure {scope:$scope,kind:'Event'})-[:EXPOSURE {role:'CONCERNS'}]->(t)
                      <-[r:EXPOSURE]-(s:AnnualExposure {kind:'Segment'})
                      <-[:EXPOSURE {role:'HAS_SEGMENT'}]-(:AnnualExposure {kind:'Company'})
                      WHERE r.role IN ['PRODUCES','USES','OPERATES','SOURCES_FROM','SERVES']
                      RETURN DISTINCT e.id AS event,t.id AS target,s.id AS segment ORDER BY event,target,segment""",
            params,
        )
        expected = {
            (entity("Event", key(e["digest"], e["target"], e["fact"])), e["target"], entity("Segment", s))
            for e in result["events"]
            for s in e["segments"]
        }
        if expected != {(p["event"], p["target"], p["segment"]) for p in read}:
            raise ValueError("Graph readback differs from audited paths")
        return {"scope": scope, "paths": read}

    return graph.verified_write(write)


def run(args):
    source = args.source
    if source.startswith(("http://", "https://")):
        raw, source = download(source)
    else:
        with Path(source).open("rb") as f:
            raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Report exceeds document limit")
    cutoff = date.today()
    doc = extract(raw, source)
    args.output.mkdir(parents=True, exist_ok=True)
    folder = args.output / "originals"
    folder.mkdir(exist_ok=True)
    issuer, pages, edges = extract_edges(doc)
    paths = routes(edges)
    tasks, trace, events, unknowns = investigate(issuer, paths, cutoff, folder)
    result = {
        "issuer": issuer,
        "as_of": str(cutoff),
        "seed_sha256": digest(raw),
        "page_count": len(doc.pages),
        "sample_pages": pages,
        "edges": edges,
        "tasks": tasks,
        "search": trace,
        "events": events,
        "unresolved_external": unknowns,
    }
    if args.neo4j:
        from src.graph.client import Neo4jClient

        with Neo4jClient() as graph:
            result["graph"] = project(graph, result)
    (args.output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    (args.output / "report.md").write_text(report_md(result))
    print(
        json.dumps(
            {
                "issuer": issuer,
                "edges": len(edges),
                "supported": sum(e["status"] == "supported" for e in edges),
                "tasks": len(tasks),
                "events": len(events),
                "paths": len(result.get("graph", {}).get("paths", [])),
            }
        )
    )
