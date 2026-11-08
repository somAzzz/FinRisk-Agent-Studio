"""Annual-report seeded research, with immutable daily evidence graphs and transition alerts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.annual_reports.analysis import excerpts
from src.annual_reports.audit import Claim, audit, key, passages, retrieve, structured, write_report
from src.annual_reports.discovery import discover
from src.annual_reports.documents import MAX_BYTES, download, extract
from src.annual_reports.financials import identity
from src.graph.client import Neo4jClient


class Task(BaseModel):
    topic: Literal["upstream", "downstream", "international"]
    scope: str
    question: str
    seed_id: str
    query: str
    terms: str
    direct_evidence_needed: str
    stop_condition: str


class Plan(BaseModel):
    tasks: list[Task] = Field(min_length=1, max_length=6)


class Proposal(BaseModel):
    text: str
    citation: str
    kind: Literal["observation", "forecast", "causal", "fulfillment"]


class Signal(BaseModel):
    state: Literal["adverse", "favorable", "mixed", "unchanged", "unknown"]
    reason: str


def read_primary(source):
    if source.startswith(("http://", "https://")):
        data, source = download(source)
    else:
        with Path(source).open("rb") as fh:
            data = fh.read(MAX_BYTES + 1)
    doc = extract(data, source)
    published = identity(doc)["published_at"]
    if not published:
        raise ValueError("An intrinsic publication date is required for replay.")
    return doc, published, data


def plan_tasks(doc, pool):
    selected = excerpts(doc, "business model raw materials customers regulation international risk", 2)
    sample = [p for p in pool.values() if p.page in selected and p.text[:80] in " ".join(selected[p.page].split())]
    if not sample:
        sample = list(pool.values())[:40]
    plan = structured(
        Plan,
        """Choose the most material, observable research question in each of upstream supply,
downstream demand or delivery, and international policy or geopolitical exposure where supported.
Use three distinct tasks if evidence permits. Anchor each question to a supplied seed passage ID.
Track a FORWARD-LOOKING unresolved exposure beyond the annual period. Never ask for a number already in the
seed. Query for subsequent official releases and external sector indicators, without guessing events or
release titles. Use English queries and include terms in BOTH languages. Specify an observable scope, evidence
needed, scope-specific stopping condition, and one web query to locate
primary publications. Include both English and source-language keywords in terms. No URLs, inferred news,
or subsequent developments. Distinguish delivery status from market risk.""",
        {"cover": identity(doc)["cover"], "passages": {p.id: p.text for p in sample[:80]}},
    )
    if any(t.seed_id not in {p.id for p in sample[:80]} for t in plan.tasks):
        raise ValueError("Planner used a citation outside its snapshot")
    return plan


def db_open(work):
    db = sqlite3.connect(work / "tracking.sqlite", timeout=120)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS snapshots (company TEXT, day TEXT, payload TEXT, PRIMARY KEY(company, day));
    CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, company TEXT, day TEXT, payload TEXT);
    """)
    return db


def snapshot(db, company, day):
    row = db.execute("SELECT payload FROM snapshots WHERE company=? AND day=?", (company, day)).fetchone()
    return json.loads(row[0]) if row else None


def build_day(plan, docs, day, previous):
    corpus = {}
    for doc, published in docs:
        if published <= day:
            corpus.update(passages(doc, published))
    from .audit import segment_note_loader

    note = segment_note_loader(docs[0][0] if docs and docs[0][1] <= day else None)
    audits, tasks, alerts = [], [], []
    nodes, edges = {}, []

    def node(node_type, identity, **properties):
        nid = key(node_type, identity)
        nodes[nid] = {**properties, "id": nid, "kind": node_type}
        return nid

    def link(src, rel, dst):
        edges.append([src, rel, dst])

    root = node("Snapshot", day.isoformat(), day=day.isoformat())

    def evidence(pid):
        p = corpus[pid]
        doc = node("Document", p.digest, source=p.source, digest=p.digest, published=p.published)
        ev = node("Evidence", pid, **{k: v for k, v in asdict(p).items() if k != "id"})
        link(ev, "FROM", doc)
        return ev

    prior = {t["id"]: t for t in previous["tasks"]} if previous else {}
    for t in plan.tasks:
        tid = key(t.topic, t.scope, t.question)
        task = node("Task", tid, **t.model_dump())
        link(root, "TRACKS", task)
        link(task, "MONITORS", node("Exposure", key(t.topic, t.scope), topic=t.topic, scope=t.scope))
        link(task, "SEEDED_BY", evidence(t.seed_id))
        current = prior.get(tid, {})
        state = current.get("state", "unknown")
        fulfillment = current.get("fulfillment", "unknown")
        fresh = {
            i: p for i, p in corpus.items() if not previous or p.digest not in previous.get("eligible_digests", [])
        }
        # Mix independently ranked term sets so a long query cannot bury its subject.
        lists = [retrieve(fresh, q, 5) for q in (t.scope, t.terms, t.question)]
        candidates = list({p.id: p for record in zip(*lists, strict=False) for p in record}.values())
        for group in lists:
            for passage in group[:2]:
                if passage not in candidates:
                    candidates.append(passage)
        if t.topic == "international":
            official = [p for p in fresh.values() if "eur-lex.europa.eu/" in p.source]
            candidates = retrieve({p.id: p for p in official}, t.scope + " " + t.terms, 2) + candidates
        candidates = candidates[:12]
        if t.seed_id in fresh and all(p.id != t.seed_id for p in candidates):
            candidates.append(corpus[t.seed_id])
        entry = {
            "id": tid,
            **t.model_dump(),
            "state": state,
            "fulfillment": fulfillment,
            "action": "await_next_publication",
        }
        prior_proofs = current.get("proofs", {})
        entry["proofs"] = prior_proofs.copy()
        if current.get("pending"):
            entry["pending"] = current["pending"]
        if candidates:
            proposed = structured(
                Proposal,
                """Propose ONE atomic dated fact, management forecast, or unresolved
fulfillment assertion addressing the task. Cite one provided ID. If no direct evidence of the requested
delivery exists, identify the missing evidence. Preserve entity, geography and period; do not substitute a
generic sector fact for company evidence. Write one clause under 28 words. Omit figures and period labels
unless essential. Prefer the latest direct observation.""",
                {"task": t.model_dump(), "as_of": str(day), "evidence": {p.id: p.text for p in candidates}},
            )
            claim = Claim(**proposed.model_dump(), topic=t.topic, scope=t.scope)
            result = audit(claim, corpus, day, note_loader=note)
            audits.append(result)
            previous_version = None
            for revision, version in enumerate(result["history"], 1):
                proposal = version["proposal"]
                verdict = version["verdict"]
                v = node("Claim", key(tid, revision, proposal), **proposal)
                link(task, "EXAMINES", v)
                if previous_version:
                    link(v, "REVISES", previous_version)
                previous_version = v
                j = node("Verdict", key(v, verdict), **verdict)
                link(v, "JUDGED_BY", j)
                if proposal["citation"] in corpus:
                    link(v, "CITES", evidence(proposal["citation"]))
                for pid in version["checked"]:
                    link(j, "CHECKED", evidence(pid))
                if verdict["evidence_id"] in corpus:
                    link(j, "DECIDED_ON", evidence(verdict["evidence_id"]))
            if result["status"] == "supported":
                signal = structured(
                    Signal,
                    """Classify only this accepted claim's implication for the task's named scope
as adverse, favorable, mixed, unchanged, or unknown. For international policy facts use unknown unless the
audited text explicitly demonstrates direction of company financial or operational impact. Legal progress
alone cannot establish a benefit. A speculative, unrelated or immaterial relationship is unknown.""",
                    {"task": t.question, "claim": proposal["text"], "original_span": verdict["quote"]},
                )
                if signal.state not in {"unknown", "unchanged"}:
                    entry.update(state=signal.state, reason=signal.reason)
                    entry["proofs"]["state"] = {"as_of": str(day), "citation": proposal["citation"], "verdict": verdict}
                if result["fulfillment"] != "unknown":
                    entry["fulfillment"] = result["fulfillment"]
                    entry["proofs"]["fulfillment"] = {
                        "as_of": str(day),
                        "citation": proposal["citation"],
                        "verdict": verdict,
                    }
                entry["action"] = "reviewed"
            if result["follow_up"]:
                follow = node(
                    "FollowUp", result["follow_up"]["id"], question=t.question, missing=result["follow_up"]["missing"]
                )
                link(j, "REQUIRES", follow)
                entry["action"] = "seek_direct_evidence"
                entry["pending"] = result["follow_up"]
            if previous and (state, fulfillment) != (entry["state"], entry["fulfillment"]):
                alert = {
                    "task": tid,
                    "previous": [state, fulfillment],
                    "current": [entry["state"], entry["fulfillment"]],
                    "day": str(day),
                    "citation": proposal["citation"],
                }
                alert["id"] = key(tid, day, alert["previous"], alert["current"])
                alerts.append(alert)
                link(node("Alert", alert["id"], **{k: v for k, v in alert.items() if k != "id"}), "BASED_ON", j)
        status = node("Status", tid, state=entry["state"], fulfillment=entry["fulfillment"])
        link(task, "HAS_STATUS", status)
        for field, proof in entry["proofs"].items():
            decision = node("VerifiedBasis", proof, **proof["verdict"], as_of=proof["as_of"])
            link(status, field.upper() + "_BASIS", decision)
            link(decision, "DECIDED_ON", evidence(proof["citation"]))
        if entry.get("pending"):
            missing = entry["pending"]
            link(
                task, "OPEN_QUESTION", node("FollowUp", missing["id"], question=t.question, missing=missing["missing"])
            )
        tasks.append(entry)
    return {
        "as_of": str(day),
        "tasks": tasks,
        "eligible_digests": sorted({p.digest for p in corpus.values()}),
        "audits": audits,
        "alerts": alerts,
        "graph": {"nodes": list(nodes.values()), "edges": [list(e) for e in sorted(set(map(tuple, edges)))]},
    }


def project(graph, company, report):
    scope = key(company, report["as_of"], report["graph"])
    params = {
        "scope": scope,
        "nodes": [
            {
                "id": n["id"],
                "kind": n["kind"],
                "published": n.get("published") or n.get("as_of"),
                "fulfillment": n.get("fulfillment"),
                "direct": n.get("direct"),
                "data": json.dumps(n, ensure_ascii=False),
            }
            for n in report["graph"]["nodes"]
        ],
        "edges": report["graph"]["edges"],
    }
    graph.run("CREATE CONSTRAINT annual_audit_id IF NOT EXISTS FOR (n:AnnualAudit) REQUIRE (n.scope,n.id) IS UNIQUE")
    graph.run(
        "UNWIND $nodes AS x MERGE (n:AnnualAudit {scope:$scope,id:x.id}) "
        "SET n.kind=x.kind,n.published=x.published,n.data=x.data, n.fulfillment=x.fulfillment,n.direct=x.direct",
        params,
    )
    graph.run(
        """UNWIND $edges AS x MATCH (a:AnnualAudit {scope:$scope,id:x[0]}),(b:AnnualAudit {scope:$scope,id:x[2]})
              MERGE (a)-[:AUDIT_LINK {role:x[1]}]->(b)""",
        params,
    )
    checks = graph.run(
        """MATCH (n:AnnualAudit {scope:$scope})
        RETURN count(n) AS nodes, sum(CASE WHEN n.published > $day THEN 1 ELSE 0 END) AS future,
        sum(CASE WHEN n.kind='Alert' THEN 1 ELSE 0 END) AS alerts""",
        {"scope": scope, "day": report["as_of"]},
    )[0]
    paths = graph.run(
        """MATCH (:AnnualAudit {scope:$scope,kind:'Alert'})-[:AUDIT_LINK {role:'BASED_ON'}]->
       (:AnnualAudit {kind:'Verdict'})-[:AUDIT_LINK {role:'DECIDED_ON'}]->(:AnnualAudit {kind:'Evidence'})
       -[:AUDIT_LINK {role:'FROM'}]->(d:AnnualAudit {kind:'Document'}) RETURN count(*) AS paths""",
        {"scope": scope},
    )[0]
    checks["unverified_fulfillment"] = graph.run(
        """MATCH (s:AnnualAudit {scope:$scope,kind:'Status'})
        WHERE s.fulfillment <> 'unknown' AND NOT EXISTS {
          MATCH (s)-[:AUDIT_LINK {role:'FULFILLMENT_BASIS'}]->(:AnnualAudit {kind:'VerifiedBasis',direct:true})
               -[:AUDIT_LINK {role:'DECIDED_ON'}]->(:AnnualAudit {kind:'Evidence'}) }
        RETURN count(s) AS violations""",
        {"scope": scope},
    )[0]["violations"]
    if (
        checks["future"]
        or checks["unverified_fulfillment"]
        or checks["nodes"] != len(params["nodes"])
        or checks["alerts"] != len(report["alerts"])
        or paths["paths"] != checks["alerts"]
    ):
        raise ValueError("Temporal or alert lineage check failed")
    return {**checks, **paths, "scope": scope}


def replay(source, dates, work, *, neo4j=False):
    doc, published, data = read_primary(source)
    work = Path(work) / doc.sha256[:16]
    work.mkdir(parents=True, exist_ok=True)
    import fcntl

    with (work / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _replay_locked(work, doc, published, data, dates, neo4j)


def _replay_locked(work, doc, published, data, dates, neo4j):
    (work / (doc.sha256 + ".pdf")).write_bytes(data)
    days = sorted(set(map(date.fromisoformat, dates)))
    if not days or min(days) < published:
        raise ValueError("Cutoff precedes the seed report publication")
    planfile = work / "tasks.json"
    if planfile.exists():
        plan = Plan.model_validate_json(planfile.read_text())
    else:
        plan = plan_tasks(doc, passages(doc, published))
        planfile.write_text(plan.model_dump_json(indent=2))
    catalog = work / "discovery.json"
    watermark = work / "discovery-through.txt"
    refresh = catalog.exists() and watermark.exists() and max(days).isoformat() > watermark.read_text().strip()
    if catalog.exists():
        import hashlib

        from src.annual_reports.documents import Document, native_pages

        docs = []
        for row in json.loads(catalog.read_text()):
            if row.get("decision") == "dated edition":
                raw = (work / (row["sha256"] + ".pdf")).read_bytes()
                if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                    raise ValueError("Evidence archive hash mismatch")
                docs.append(
                    (Document(row["url"], row["sha256"], native_pages(raw)), date.fromisoformat(row["published"]))
                )
    else:
        docs, trace = discover(doc, [t.query for t in plan.tasks], work)
        catalog.write_text(json.dumps(trace, indent=2))
    if refresh:
        queries = [t.query for t in plan.tasks]
        with db_open(work) as previous_db:
            last = previous_db.execute(
                "SELECT payload FROM snapshots WHERE company=? AND day<? ORDER BY day DESC LIMIT 1",
                (doc.sha256, max(days).isoformat()),
            ).fetchone()
        if last:
            for task in json.loads(last[0])["tasks"]:
                if task.get("pending"):
                    queries.append(task["scope"] + " " + task["direct_evidence_needed"])
        new_docs, trace = discover(doc, queries, work)
        known = {d.sha256 for d, _ in docs}
        docs.extend((d, p) for d, p in new_docs if d.sha256 not in known)
        catalog.write_text(json.dumps(json.loads(catalog.read_text()) + trace, indent=2))
    if not watermark.exists() or refresh:
        watermark.write_text(max(days).isoformat())
    docs = [(doc, published)] + [(d, p) for d, p in docs if d.sha256 != doc.sha256]
    db = db_open(work)
    summary = []
    try:
        for day in days:
            iso = str(day)
            with db:
                db.execute("BEGIN IMMEDIATE")
                report = snapshot(db, doc.sha256, iso)
                inserted = 0
                if report is None:
                    last = db.execute(
                        "SELECT day,payload FROM snapshots WHERE company=? ORDER BY day DESC LIMIT 1", (doc.sha256,)
                    ).fetchone()
                    if last and last[0] > iso:
                        raise ValueError("Use a new replay directory to insert a historical cutoff")
                    report = build_day(plan, docs, day, json.loads(last[1]) if last else None)
                    for alert in report["alerts"]:
                        inserted += db.execute(
                            "INSERT OR IGNORE INTO alerts VALUES(?,?,?,?)",
                            (alert["id"], doc.sha256, iso, json.dumps(alert)),
                        ).rowcount
                    db.execute("INSERT INTO snapshots VALUES(?,?,?)", (doc.sha256, iso, json.dumps(report)))
            checks = {}
            if neo4j:
                with Neo4jClient() as graph:
                    checks = project(graph, doc.sha256, report)
            write_report(work / (iso + ".json"), report)
            summary.append({"as_of": iso, "new_alerts": inserted, "graph": checks, "tasks": len(report["tasks"])})
    finally:
        db.close()
    return summary
