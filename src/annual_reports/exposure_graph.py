"""Project a dated exposure view and verify paths against its original P0 alerts."""

import json

from .audit import key


def project_exposures(graph, report):
    graph.run(
        "CREATE CONSTRAINT annual_exposure_id IF NOT EXISTS FOR (n:AnnualExposure) REQUIRE (n.scope,n.id) IS UNIQUE"
    )
    return graph.verified_write(lambda run: _project_and_check(run, report))


def _project_and_check(run, report):
    scope = key("exposure-v1", report)
    params = {"scope": scope, "day": report["as_of"], "edges": report["edges"]}
    nodes = [
        *report["nodes"],
        *[
            {**citation, "id": f"Evidence/{eid}", "document_kind": citation["kind"], "kind": "Evidence", "name": eid}
            for eid, citation in report["evidence"].items()
        ],
    ]
    params["nodes"] = [{**n, "data": json.dumps(n, ensure_ascii=False)} for n in nodes]
    refs = [n for n in nodes if "p0_id" in n]
    params["refs"] = refs
    # One transaction joins only existing audit anchors. An absent P0 scope skips the entire write.
    counts = run(
        """
        CALL () { UNWIND $refs AS ref MATCH (a:AnnualAudit {scope:ref.p0_scope,id:ref.p0_id,kind:'Alert'})
               RETURN count(a) AS matched }
        WITH matched WHERE matched=size($refs)
        CALL () { UNWIND $nodes AS x MERGE (n:AnnualExposure {scope:$scope,id:x.id})
               SET n.kind=x.kind,n.name=x.name,n.data=x.data,n.published=x.published,n.status=x.status,
                   n.jurisdiction=x.jurisdiction,n.change=x.change,n.unit=x.unit RETURN count(*) AS nodes }
        CALL () { UNWIND $edges AS x MATCH (a:AnnualExposure {scope:$scope,id:x.subject}),
                                        (b:AnnualExposure {scope:$scope,id:x.object})
               MERGE (a)-[r:EXPOSURE {role:x.relation,evidence:x.evidence}]->(b)
               SET r.published=x.published,r.provenance=x.provenance RETURN count(*) AS edges }
        CALL () { UNWIND $refs AS ref MATCH (a:AnnualAudit {scope:ref.p0_scope,id:ref.p0_id}),
                                          (b:AnnualExposure {scope:$scope,id:ref.id})
               MERGE (b)-[:REFERS_TO]->(a) RETURN count(*) AS anchors }
        RETURN nodes,edges,anchors
    """,
        params,
    )
    if not counts or counts[0] != {"nodes": len(nodes), "edges": len(params["edges"]), "anchors": len(refs)}:
        raise ValueError("P1 projection incomplete. Project the matching P0 tracking snapshots first.")
    checks = run(
        """
        MATCH (n:AnnualExposure {scope:$scope})
        OPTIONAL MATCH (n)-[r:EXPOSURE]->(b)
        OPTIONAL MATCH (e:AnnualExposure {scope:$scope,kind:'Evidence',name:r.evidence})
        RETURN count(DISTINCT n) AS nodes,sum(CASE WHEN r IS NULL THEN 0 ELSE 1 END) AS relationships,
        sum(CASE WHEN n.published > $day OR r.published > $day OR b.scope <> $scope
                 THEN 1 ELSE 0 END) AS future_or_cross_scope,
        sum(CASE WHEN r IS NOT NULL AND (e IS NULL OR e.published <> r.published)
                 THEN 1 ELSE 0 END) AS missing_citations
    """,
        params,
    )[0]
    traces = run(
        """
        MATCH (a:AnnualAudit {kind:'Alert'})<-[:REFERS_TO]-(ref:AnnualExposure {scope:$scope})
          -[:EXPOSURE {role:'CONCERNS'}]->(p)<-[r:EXPOSURE]-(s:AnnualExposure {kind:'Segment'})
          -[:EXPOSURE {role:'REPORTED'}]->(m:AnnualExposure {kind:'Metric'})
        WHERE r.role IN ['USES','SELLS'] AND r.provenance='annual_report_disclosure'
        RETURN a.id AS alert,s.id AS segment,m.id AS metric,m.change AS change,m.unit AS unit
        ORDER BY alert,metric
    """,
        params,
    )
    policy_paths = run(
        """
        MATCH (:AnnualExposure {scope:$scope,kind:'Assigned task'})-[:EXPOSURE {role:'TRACKS'}]->
              (o)-[:EXPOSURE {role:'MAY_AFFECT', provenance:'model_inference'}]->(c)
              -[:EXPOSURE {role:'MAY_REDUCE_PURCHASES_OF', provenance:'model_inference'}]->(p)
              <-[:EXPOSURE {role:'SELLS', provenance:'annual_report_disclosure'}]-(s)
        RETURN DISTINCT o.jurisdiction AS jurisdiction, c.name AS customer_class, p.name AS product, s.name AS segment
        ORDER BY jurisdiction, customer_class, product, segment
    """,
        params,
    )
    if report["tax_scenario"] and (
        not policy_paths or any(path["jurisdiction"] != report["target_jurisdiction"] for path in policy_paths)
    ):
        raise ValueError("Missing or cross-jurisdiction policy exposure path")
    expected = sorted(
        (a["alert"], a["segment"], f"Metric/{a['segment']}/H1 2026-27/{metric}", values["change"], "EUR million")
        for a in report["alerts"]
        for metric, values in a["actuals"].items()
    )
    observed = sorted((r["alert"], r["segment"], r["metric"], r["change"], r["unit"]) for r in traces)
    policies = run(
        """
        MATCH (:AnnualExposure {scope:$scope,kind:'Assigned task'})-[r:EXPOSURE]->
              (s:AnnualExposure {kind:'Policy observation'})
        WHERE r.role IN ['TRACKS','COMPARES']
        WITH s.jurisdiction AS jurisdiction,s.status AS status,r.published AS day,r.role AS role
        ORDER BY day DESC
        RETURN jurisdiction,collect([status,day,role])[0] AS latest ORDER BY jurisdiction
    """,
        params,
    )
    expected_policy = {
        k: [v["status"], v["published"], "TRACKS" if k == report["target_jurisdiction"] else "COMPARES"]
        for k, v in report["policies"].items()
    }
    if (
        observed != expected
        or {r["jurisdiction"]: r["latest"] for r in policies} != expected_policy
        or checks["future_or_cross_scope"]
        or checks["missing_citations"]
        or checks["nodes"] != len(nodes)
        or checks["relationships"] != len(params["edges"])
    ):
        raise ValueError(f"Exposure graph readback mismatch: {checks}")
    return {
        **checks,
        "scope": scope,
        "original_alerts": len(refs),
        "metric_paths": traces,
        "policy_exposure_paths": policy_paths,
        "policy_readback": policies,
    }
