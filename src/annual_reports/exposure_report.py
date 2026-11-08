"""English replay reports for evidence-backed exposure graphs."""

import json
from decimal import Decimal

from .exposure import build


def markdown(r):
    lines = [
        f"# {r['company']} exposure review · {r['as_of']}",
        "",
        "## Tracked alerts and reported performance",
        "",
        "H1 covers March to August. Figures are EUR million. Operating profit uses the issuer's operating result.",
        "",
        "| Segment | Metric | H1 2025/26 | H1 2026/27 | Actual change | Event-attributable change |",
        "|---|---|---:|---:|---:|---|",
    ]

    def source(eid):
        e = r["evidence"][eid]
        label = f"{e['published']}" + (f", PDF p. {e['page']}" if e["page"] else "")
        return f"[{label}]({e['url']})"

    for alert in r["alerts"]:
        for metric, values in alert["actuals"].items():
            segment = alert["segment"].split("/", 1)[1]
            field = "attributable_revenue" if metric == "Revenues" else "attributable_operating_result"
            lines.append(
                f"| {segment} | {metric} | {values['prior']:,} | {values['current']:,} "
                f"| {values['change']:+,} | {alert[field]} |"
            )
    for a in r["alerts"]:
        segment = a["segment"].split("/", 1)[1]
        lines.extend(
            [
                "",
                f"**{segment}.** The {a['day']} alert concerns {a['product'].split('/', 1)[1].lower()}. "
                f"{a['interpretation']} Contract fulfillment remains **{a['fulfillment']}**. "
                f"Alert evidence {source(a['evidence'])}. Financial table {source(a['financial_evidence'])}.",
            ]
        )
    lines.extend(
        [
            "",
            "### Illustrative sensitivities",
            "",
            "The inputs are analyst assumptions. All other revenues, fixed costs and depreciation are held constant.",
        ]
    )
    for alert in r["alerts"]:
        s = alert["scenario"]
        a = s["assumptions"]
        lines.extend(
            [
                "",
                f"- **{a['segment']}**. Starting volume {Decimal(a['tonnes']):,} t, selling price EUR {a['price']}/t "
                f"and variable cost EUR {a['variable_cost']}/t. A {Decimal(a['volume_change']):+.0%} volume change "
                f"and EUR {Decimal(a['price_change_per_tonne']):+}/t price change give "
                f"EUR {Decimal(s['revenue_delta']):+,.0f} revenue and "
                f"EUR {Decimal(s['contribution_after_idle_cost_delta']):+,.0f} operating result, all else fixed.",
            ]
        )
    lines.extend(
        [
            "",
            f"## Assigned task · {r['policy_task']}",
            "",
            "| Jurisdiction | Latest evidenced status | Effective date established | Evidence |",
            "|---|---|---|---|",
        ]
    )
    for country, state in r["policies"].items():
        lines.append(
            f"| {country} | {state['status']} | {state.get('effective', 'unknown')} | {source(state['evidence'])} |"
        )
    lines.extend(
        [
            "",
            "The French schedule applies in France. The Commission supports coordination among member states. "
            "The cited EU evidence establishes no common rate. German milestones follow.",
        ]
    )
    lines.append("")
    for e in r["edges"]:
        if e["relation"] == "TRACKS":
            lines.append(f"- {e['object'].split('/')[-1]} · {source(e['evidence'])}")
    for note in r["policy_notes"]:
        lines.extend(["", f"{note['text']} {source(note['evidence'])}"])
    if s := r["tax_scenario"]:
        a = s["assumptions"]
        lines.extend(
            [
                "",
                "German producers could reformulate drinks or sell fewer taxable litres. "
                "The Sugar segment could see lower liquid sugar orders. "
                "Buyers, German taxable volumes, sourcing shares and company-specific effects remain unknown. "
                "The disclosed Fruit-to-beverage customer relationship alone cannot establish taxable juice sales.",
                "",
                f"**German reformulation scenario.** At {a['litres']:,} L, {a['grams_removed_per_litre']} g/L "
                "of sugar removed "
                f"and an assumed {a['supplier_share']:.0%} supplier share, volume falls by {s['tonnes_removed']:g} t. "
                f"At EUR {a['price_per_tonne']}/t and EUR {a['variable_cost_per_tonne']}/t variable cost, "
                "modeled revenue changes by "
                f"EUR {s['revenue_delta']:+,.0f} and operating result by "
                f"EUR {s['operating_result_delta_fixed_other_costs']:+,.0f}, all else fixed.",
            ]
        )
    lines.extend(
        [
            "",
            "## Relationship evidence",
            "",
            "Customer classes represent markets served. Buyers and region-to-factory routes remain unknown.",
            "",
            "| From | Relationship | To | Provenance | Source |",
            "|---|---|---|---|---|",
        ]
    )
    for e in r["edges"]:
        if (
            e["subject"].split("/", 1)[0] in {"Company", "Segment", "Growing region", "Plant", "Customer class"}
            and e["relation"] != "REPORTED"
        ):
            lines.append(
                f"| {e['subject']} | {e['relation']} | {e['object']} | "
                f"{e['provenance'].replace('_', ' ')} | {source(e['evidence'])} |"
            )
    if g := r.get("neo4j"):
        lines.extend(
            [
                "",
                "## Graph verification",
                "",
                f"Graph readback found {g['original_alerts']} distinct original alert references, "
                f"{len(g['metric_paths'])} alert-to-metric paths, {g['missing_citations']} missing citations and "
                f"{g['future_or_cross_scope']} future or cross-snapshot observations. "
                "The accompanying JSON records the paths, policy states and source fingerprints.",
            ]
        )
    if r["unmapped_alerts"]:
        lines.append(f"\nUnmapped alerts requiring review: {len(r['unmapped_alerts'])}.")
    return "\n".join(lines) + "\n"


def run(args):
    case = json.loads(args.case.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    for day in sorted(set(args.as_of)):
        r = build(case, args.tracking, args.sources, day, args.fetch)
        if args.neo4j:
            from src.graph.client import Neo4jClient

            from .exposure_graph import project_exposures

            with Neo4jClient() as graph:
                r["neo4j"] = project_exposures(graph, r)
        for ext, content in [("json", json.dumps(r, ensure_ascii=False, indent=2) + "\n"), ("md", markdown(r))]:
            path = args.output / f"{day}.{ext}"
            path.write_text(content, encoding="utf-8")
        print(f"{day}  {len(r['alerts'])} mapped alerts  {args.output / (day + '.md')}")
