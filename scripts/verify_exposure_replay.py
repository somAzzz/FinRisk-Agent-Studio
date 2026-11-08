"""Verify the archived Südzucker P1 case against the configured tracking graph."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from src.annual_reports.audit import key
from src.annual_reports.exposure import build
from src.annual_reports.exposure_graph import project_exposures
from src.graph.client import Neo4jClient


def check(args):
    case = json.loads(args.case.read_text())
    days = ["2026-11-08", "2026-10-08"] * 2
    snapshots = {}
    with Neo4jClient() as graph:
        for day in days:
            replay = build(case, args.tracking, args.sources, day)
            if replay["unmapped_alerts"] or len(replay["alerts"]) != 2:
                raise ValueError("Expected both October alerts to have verified segment exposures")
            replay["neo4j"] = project_exposures(graph, replay)
            if day in snapshots and snapshots[day] != replay:
                raise ValueError(f"Repeat replay changed {day}")
            snapshots[day] = replay
        october = snapshots["2026-10-08"]
        # Change only the reported delta. The graph must reject it and roll back the candidate scope.
        wrong = deepcopy(october)
        del wrong["neo4j"]
        wrong["alerts"][0]["actuals"]["Revenues"]["change"] += 1
        try:
            project_exposures(graph, wrong)
        except ValueError as exc:
            if "readback mismatch" not in str(exc):
                raise
        else:
            raise ValueError("Misstated revenue change passed graph verification")
        residual = graph.run(
            "MATCH (n:AnnualExposure {scope:$scope}) RETURN count(n) AS n", {"scope": key("exposure-v1", wrong)}
        )[0]["n"]
        scope = next(n["p0_scope"] for n in october["nodes"] if "p0_scope" in n)
        originals = graph.run(
            "MATCH (a:AnnualAudit {scope:$scope,kind:'Alert'}) RETURN a.id AS id ORDER BY id", {"scope": scope}
        )
        expected_ids = sorted(a["alert"] for a in october["alerts"])
        if residual or expected_ids != [a["id"] for a in originals]:
            raise ValueError("Unexpected residual nodes or changed original alerts")
    return {
        "replay_order": days,
        "identical_on_repeat": True,
        "rejected_wrong_financial_delta": True,
        "failed_projection_nodes": residual,
        "original_alert_ids": expected_ids,
        "scopes": {day: r["neo4j"]["scope"] for day, r in snapshots.items()},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("config/annual_reports/suedzucker-p1.json"))
    parser.add_argument("--tracking", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=Path(".cache/p1/sources"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args), indent=2) + "\n")
