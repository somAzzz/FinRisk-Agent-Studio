"""Check replay artifacts independently, including actual Neo4j paths and the SQLite alert ledger."""

import argparse
import json
import sqlite3
from pathlib import Path

from src.graph.client import Neo4jClient


def verify(work, first, repeat, cases):
    assert len(first) == len(repeat) > 0
    verdicts = [[v["verdict"]["status"] for v in a["history"]] for a in cases["audits"]]
    assert verdicts[0] == ["supported"]
    assert verdicts[1][0] == "contradicted" and verdicts[1][-1] == "supported"
    assert verdicts[2][0] == "wrong_citation" and verdicts[2][-1] == "supported"
    assert cases["audits"][3]["follow_up"] and cases["audits"][3]["fulfillment"] == "unknown"
    with Neo4jClient() as graph, sqlite3.connect(work / "tracking.sqlite") as db:
        output = []
        for run, again in zip(first, repeat, strict=True):
            day = run["as_of"]
            assert again["as_of"] == day and again["new_alerts"] == 0 and run["graph"] == again["graph"]
            stored = json.loads(db.execute("SELECT payload FROM snapshots WHERE day=?", (day,)).fetchone()[0])
            report = json.loads((work / (day + ".json")).read_text())
            assert stored["graph"] == report["graph"]
            assert all(n.get("published", day) <= day for n in report["graph"]["nodes"])
            assert all(t["fulfillment"] == "unknown" for t in report["tasks"])
            ledger = {r[0] for r in db.execute("SELECT id FROM alerts WHERE day=?", (day,))}
            assert len(ledger) == run["new_alerts"] and ledger == {a["id"] for a in report["alerts"]}
            evidence = graph.run(
                """MATCH (a:AnnualAudit {scope:$scope, kind:'Alert'})
                  -[:AUDIT_LINK {role:'BASED_ON'}]->(v)-[:AUDIT_LINK {role:'DECIDED_ON'}]->(e)
                  -[:AUDIT_LINK {role:'FROM'}]->(d)
                  RETURN a.data AS alert,v.data AS verdict,e.data AS evidence,d.published AS publication""",
                {"scope": run["graph"]["scope"]},
            )
            assert len(evidence) == len(ledger)
            for path in evidence:
                verdict = json.loads(path["verdict"])
                assert path["publication"] <= day and verdict["status"] == "supported"
                assert verdict["quote"] in json.loads(path["evidence"])["text"]
            output.append(
                {
                    "as_of": day,
                    "alerts": len(ledger),
                    "verified_alert_paths": len(evidence),
                    "repeat_insertions": again["new_alerts"],
                    "unknown_fulfillment": len(report["tasks"]),
                    "future_nodes": run["graph"]["future"],
                    "graph_scope": run["graph"]["scope"],
                }
            )
    return {"source": "Südzucker 2025/26", "audit_case_histories": verdicts, "replay": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "first", "repeat", "cases"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.work, *[json.loads(getattr(args, k).read_text()) for k in ("first", "repeat", "cases")]),
            indent=2,
        )
    )
