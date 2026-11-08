# Südzucker P1 replay

[8 October report](2026-10-08.md) · [8 November report](2026-11-08.md) · [Graph regression results](verification.json)

The reviewed case manifest maps six entity types and records the source for each relationship. The replay resolves existing P0 alert identities, validates their verdicts against the original PDF pages, extracts the H1 table columns, and checks the resulting paths in Neo4j. Company interim disclosures have their own provenance value. The Wabern permit independently identifies the operator and input. Customer nodes are classes where buyers are unnamed. The German policy task was assigned by the user.

The replay reconstructs the public evidence available by each cutoff from documents collected later. It uses publication dates at day resolution. Its coverage is the reviewed source set and selected relationships for these alerts. Another issuer or table layout requires a reviewed mapping. The source archive, located in the P0 company directory and the P1 source cache, pins original bytes by SHA-256. The JSON reports contain source URLs, page anchors, assumptions, graph scopes and verification paths.

Run from the repository root with Poppler and the project's Python environment. Set the same Neo4j connection used for P0. Use the company directory produced by `track-report` with its original graph projected.

```bash
python main.py exposure-replay \
  --case config/annual_reports/suedzucker-p1.json \
  --tracking .cache/p0/verified/597193d6e3ff8ba3 \
  --as-of 2026-10-08 2026-11-08 \
  --output docs/reports/suedzucker-p1 --neo4j

python -m scripts.verify_exposure_replay \
  --tracking .cache/p0/verified/597193d6e3ff8ba3 \
  --output docs/reports/suedzucker-p1/verification.json
```

`--fetch` retrieves missing public originals and checks their stored fingerprints. If a publisher changes the underlying bytes, replay requires the pinned copy. Running without `--neo4j` produces a local report without database readback.

To inspect a financial path, bind `$scope` to the dated JSON report's `neo4j.scope`. The returned event and table evidence IDs resolve in that report's `evidence` dictionary or its `AnnualExposure` evidence nodes.

```cypher
MATCH (a:AnnualAudit {kind:'Alert'})<-[:REFERS_TO]-(ref:AnnualExposure {scope:$scope})
      -[event:EXPOSURE {role:'CONCERNS'}]->(product)
      <-[supply:EXPOSURE]-(segment:AnnualExposure {kind:'Segment'})
      -[disclosure:EXPOSURE {role:'REPORTED'}]->(metric)
WHERE supply.role IN ['USES','SELLS']
RETURN a.id, product.name, segment.name, metric.name, metric.change, metric.unit,
       event.evidence, disclosure.evidence
```
