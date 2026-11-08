"""Point-in-time supply-chain and policy exposures over audited tracking snapshots."""

from __future__ import annotations

# ruff: noqa: RUF001 -- preserve the dash used in the issuer's printed table.
import hashlib
import json
import re
import subprocess
from datetime import date
from decimal import Decimal
from functools import cache as memoize

from bs4 import BeautifulSoup

from .analysis import Shock
from .audit import key
from .documents import download


def normalized(text):
    return " ".join(re.sub(r"(?<=\w)-\s+(?=[a-zäöü])", "", text.replace("\xad", "")).split())


class EvidenceBook:
    def __init__(self, case, archive, cache, day, fetch):
        self.case = case
        self.archive = archive
        self.cache = cache
        self.day = day
        self.fetch = fetch
        self.used = {}
        self.original = memoize(self.original)
        self.page = memoize(self.page)
        self.verify_publication = memoize(self.verify_publication)

    def original(self, name):
        doc = self.case["documents"][name]
        if date.fromisoformat(doc["published"]) > self.day:
            raise ValueError(f"Future document: {name}")
        filename = doc["sha256"] + "." + doc["format"]
        for directory in (self.archive, self.cache):
            path = directory / filename
            if path.exists():
                raw = path.read_bytes()
                break
        else:
            if not self.fetch:
                raise FileNotFoundError(f"Missing pinned source {filename} ({doc['url']})")
            raw, _ = download(doc["url"], discover_pdf=False)
        if hashlib.sha256(raw).hexdigest() != doc["sha256"]:
            raise ValueError(f"Source fingerprint mismatch: {name}")
        if not path.exists():
            self.cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return path

    def page(self, name, page, layout=False):
        path = self.original(name)
        if page is None:
            return BeautifulSoup(path.read_bytes(), "html.parser").get_text(" ", strip=True)
        return subprocess.check_output(
            ["pdftotext", "-layout" if layout else "-raw", "-f", str(page), "-l", str(page), str(path), "-"],
            encoding="utf-8",
        )

    def verify_publication(self, name):
        doc = self.case["documents"][name]
        if doc["kind"] != "authority":
            return  # Issuer dates are also bound to the originating P0 snapshot.
        day = date.fromisoformat(doc["published"])
        months = [
            "Januar",
            "Februar",
            "März",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        ]
        stamps = (day.strftime("%d/%m/%Y"), day.strftime("%d.%m.%Y"), f"{day.day}. {months[day.month - 1]} {day.year}")
        if doc["format"] == "html":
            soup = BeautifulSoup(self.original(name).read_bytes(), "html.parser")
            dates = " ".join(x.get_text(" ", strip=True) for x in soup.select("title, h1, time"))
            if doc.get("instrument") == "tax_schedule":
                dates = self.page(name, None)
        else:
            dates = self.page(name, 1)
        if not any(stamp in normalized(dates) for stamp in stamps):
            raise ValueError(f"Publication date missing from authority document: {name}")

    def cite(self, evidence):
        entry = self.case["evidence"][evidence]
        doc = self.case["documents"][entry["document"]]
        if date.fromisoformat(doc["published"]) > self.day:
            return None
        self.verify_publication(entry["document"])
        text = normalized(self.page(entry["document"], entry["page"]))
        if not entry["anchors"] or any(not anchor.strip() for anchor in entry["anchors"]):
            raise ValueError(f"Empty evidence anchor: {evidence}")
        if any(normalized(anchor) not in text for anchor in entry["anchors"]):
            raise ValueError(f"Source anchor missing: {evidence}")
        self.used[evidence] = {**entry, **doc}
        return self.used[evidence]


def half_year_actuals(page, segment):
    """Select H1 columns only after verifying the table's period, unit and segment."""
    header = f"Business performance – {segment} segment"
    if header not in page:
        raise ValueError(f"Missing segment table: {segment}")
    table = page.split(header, 1)[1]
    if not re.search(r"2nd quarter\s+1st half year\s+2026/27\s+2025/26\s+\+ / – in %\s+2026/27\s+2025/26", table):
        raise ValueError("Unrecognized quarter / half-year column order")
    actuals = {}
    for label in ("Revenues", "Operating result"):
        rows = re.findall(rf"^\s*{label}\s+€ million\s+([^\n]+)", table, re.M)
        if len(rows) != 1:
            raise ValueError(f"Missing or ambiguous {label} row")
        fields = re.split(r"\s{2,}", rows[0].strip())
        if len(fields) != 6:
            raise ValueError(f"Unexpected {label} columns: {fields}")

        def amount(value):
            if not re.fullmatch(r"[–-]?\s*(?:\d+|\d{1,3}(?:,\d{3})+)", value):
                raise ValueError(f"Invalid million-euro amount: {value}")
            return int(value.replace("–", "-").replace(" ", "").replace(",", ""))

        current, prior = map(amount, fields[3:5])
        actuals[label] = {"current": current, "prior": prior, "change": current - prior}
    return actuals


def audit_lineage(snapshot, alert):
    nodes = {n["id"]: n for n in snapshot["graph"]["nodes"]}

    def follow(node, role):
        targets = [nodes[b] for a, r, b in snapshot["graph"]["edges"] if (a, r) == (node["id"], role)]
        if len(targets) != 1:
            raise ValueError(f"Ambiguous or missing P0 {role} edge")
        return targets[0]

    verdict = follow(alert, "BASED_ON")
    evidence = follow(verdict, "DECIDED_ON")
    doc = follow(evidence, "FROM")
    if (
        verdict["status"] != "supported"
        or alert["citation"] != verdict["evidence_id"]
        or normalized(verdict["quote"]) not in normalized(evidence["text"])
        or evidence["id"] != key("Evidence", verdict["evidence_id"])
        or not verdict["quote"].strip()
        or doc["digest"] != evidence["digest"]
        or doc["published"] != evidence["published"]
        or doc["published"] > alert["day"]
        or alert["day"] != snapshot["as_of"]
    ):
        raise ValueError("Invalid P0 alert lineage")
    if alert["current"][1] != "unknown":
        status = nodes[key("Status", alert["task"])]
        proof = follow(status, "FULFILLMENT_BASIS")
        basis = follow(proof, "DECIDED_ON")
        if (
            not proof.get("direct")
            or proof.get("fulfillment") != alert["current"][1]
            or proof["as_of"] > alert["day"]
            or basis["published"] > alert["day"]
            or basis["id"] != key("Evidence", proof["evidence_id"])
        ):
            raise ValueError("Missing direct fulfillment evidence")
    return evidence, verdict


def build(case, archive, cache, as_of, fetch=False):
    day = date.fromisoformat(as_of)
    book = EvidenceBook(case, archive, cache, day, fetch)
    nodes, edges, alerts, unmapped = {}, [], [], []

    def node(identifier, **attrs):
        kind, name = identifier.split("/", 1)
        nodes[identifier] = {**nodes.get(identifier, {}), "id": identifier, "kind": kind, "name": name, **attrs}
        return identifier

    def link(a, role, b, evidence, inferred=False):
        cite = book.cite(evidence)
        if cite is None:
            return
        provenance = (
            "model_inference"
            if inferred
            else {
                "annual_report": "annual_report_disclosure",
                "interim_report": "issuer_interim_disclosure",
                "authority": "external_confirmation",
            }[cite["kind"]]
        )
        edges.append(
            {
                "subject": node(a),
                "relation": role,
                "object": node(b),
                "evidence": evidence,
                "provenance": provenance,
                "published": cite["published"],
            }
        )

    for item in case["relationships"]:
        link(item["subject"], item["relation"], item["object"], item["evidence"], item.get("inference", False))

    policy = case["policy_task"]
    task = "Assigned task/" + policy["name"]
    node(task, origin=policy["origin"], jurisdiction=policy["jurisdiction"])
    policies = {}
    for state in policy["states"]:
        cite = book.cite(state["evidence"])
        if not cite:
            continue
        country = state["jurisdiction"]
        if cite.get("jurisdiction") != country:
            raise ValueError(f"Jurisdiction mismatch for {state['evidence']}")
        if state["status"] == "in force" and (
            cite.get("instrument") not in {"tax_schedule", "enacted_law"}
            or not state.get("effective")
            or date.fromisoformat(state["effective"]) > day
        ):
            raise ValueError("An in-force policy requires an eligible effective date")
        sid = "Policy observation/" + country + "/" + state["status"]
        node(sid, jurisdiction=country, status=state["status"], effective=state.get("effective"))
        link(task, "TRACKS" if country == policy["jurisdiction"] else "COMPARES", sid, state["evidence"])
        if country == policy["jurisdiction"]:
            link(sid, "MAY_AFFECT", policy["customer"], state["evidence"], True)
        if country not in policies or cite["published"] > policies[country]["published"]:
            policies[country] = {**state, "published": cite["published"]}
    # Convert grams to metric tonnes before applying the assumed supplier share.
    tax_scenario = None
    if policy["jurisdiction"] in policies:
        a = {k: Decimal(str(v)) for k, v in policy["assumptions"].items()}
        if any(v < 0 or not v.is_finite() for v in a.values()) or a["supplier_share"] > 1:
            raise ValueError("Invalid reformulation assumptions")
        tonnes = a["litres"] * a["grams_removed_per_litre"] * a["supplier_share"] / 1_000_000
        tax_scenario = {
            "assumptions": policy["assumptions"],
            "tonnes_removed": float(tonnes),
            "revenue_delta": float(-tonnes * a["price_per_tonne"]),
            "operating_result_delta_fixed_other_costs": float(
                -tonnes * (a["price_per_tonne"] - a["variable_cost_per_tonne"])
            ),
            "currency": "EUR",
            "attributable_amount": "unknown",
        }
        scenario_id = "Scenario/" + policy["name"]
        node(scenario_id, **tax_scenario)
        link(task, "HAS_SCENARIO", scenario_id, policies[policy["jurisdiction"]]["evidence"], True)
    snapshots = sorted(p for p in archive.glob("????-??-??.json") if date.fromisoformat(p.stem) <= day)
    if not snapshots:
        raise ValueError("No eligible tracking snapshot")
    annual = case["documents"][case["annual_document"]]["sha256"]
    for path in snapshots:
        snap = json.loads(path.read_text())
        if snap["as_of"] != path.stem or not any(
            n.get("digest") == annual and n["kind"] == "Document" for n in snap["graph"]["nodes"]
        ):
            raise ValueError(f"Wrong tracking snapshot: {path}")
        for alert in (n for n in snap["graph"]["nodes"] if n["kind"] == "Alert"):
            ev, verdict = audit_lineage(snap, alert)
            matched = False
            for mapping in case["alert_cases"]:
                ref = book.cite(mapping["evidence"])
                if not ref or (ref["sha256"], ref["page"]) != (ev["digest"], ev["page"]):
                    continue
                if not all(normalized(x) in normalized(verdict["quote"]) for x in ref["anchors"]):
                    continue
                if ref["published"] != ev["published"]:
                    raise ValueError("Issuer date differs from P0 source")
                if normalized(verdict["quote"]) not in normalized(book.page(ref["document"], ref["page"])):
                    raise ValueError("Alert quote absent from pinned original")
                segment, product = mapping["segment"], mapping["product"]
                if not any(
                    e["subject"] == segment and e["object"] == product and e["provenance"] == "annual_report_disclosure"
                    for e in edges
                ):
                    raise ValueError("No disclosed product-to-segment path")
                source = book.cite(mapping["financial_evidence"])
                if not source:
                    continue
                actuals = half_year_actuals(
                    book.page(source["document"], source["page"], True), segment.split("/", 1)[1]
                )
                anchor = "Alert reference/" + alert["id"]
                node(anchor, p0_scope=key(annual, snap["as_of"], snap["graph"]), p0_id=alert["id"])
                link(anchor, "CONCERNS", product, mapping["evidence"])
                for metric, values in actuals.items():
                    mid = f"Metric/{segment}/H1 2026-27/{metric}"
                    node(mid, period="H1 2026/27", comparison="H1 2025/26", unit="EUR million", **values)
                    link(segment, "REPORTED", mid, mapping["financial_evidence"])
                matched = True
                node(
                    anchor,
                    attributable_revenue="unknown",
                    attributable_operating_result="unknown",
                    fulfillment=alert["current"][1],
                )
                scenario = Shock.model_validate(mapping["scenario"]).impact()
                scenario_id = "Scenario/" + alert["id"]
                node(scenario_id, **scenario)
                link(anchor, "HAS_SCENARIO", scenario_id, mapping["evidence"], True)
                alerts.append(
                    {
                        "alert": alert["id"],
                        "day": alert["day"],
                        "published": ref["published"],
                        "evidence": mapping["evidence"],
                        "product": product,
                        "segment": segment,
                        "fulfillment": alert["current"][1],
                        "actuals": actuals,
                        "financial_evidence": mapping["financial_evidence"],
                        "interpretation": mapping["interpretation"],
                        "attributable_revenue": "unknown",
                        "attributable_operating_result": "unknown",
                        "scenario": scenario,
                    }
                )
            if not matched:
                unmapped.append(
                    {"alert": alert["id"], "scope": snap["as_of"], "reason": "No verified exposure mapping"}
                )
    if len({a["alert"] for a in alerts}) != len(alerts):
        raise ValueError("Duplicate alert mapping")
    return json.loads(
        json.dumps(
            {
                "company": case["company"],
                "as_of": as_of,
                "nodes": list(nodes.values()),
                "edges": edges,
                "evidence": book.used,
                "alerts": alerts,
                "policy_task": policy["name"],
                "policies": policies,
                "policy_notes": [n for n in policy.get("notes", []) if book.cite(n["evidence"])],
                "tax_scenario": tax_scenario,
                "target_jurisdiction": policy["jurisdiction"],
                "unmapped_alerts": unmapped,
            },
            default=str,
        )
    )
