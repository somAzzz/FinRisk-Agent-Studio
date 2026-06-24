import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import type { RiskReport as RiskReportType } from "../types";

interface Props {
  report: RiskReportType | null;
  companyName?: string | null;
}

interface GraphData {
  nodes: Node[];
  edges: Edge[];
}

function buildGraph(
  report: RiskReportType,
  companyName: string | null,
): GraphData {
  const company = companyName || "Company";
  const companyId = "company";
  const nodes: Node[] = [
    {
      id: companyId,
      data: { label: company },
      position: { x: 0, y: 0 },
      style: {
        background: "#10b981",
        color: "white",
        borderRadius: 6,
        padding: 8,
        fontWeight: 600,
        fontSize: 12,
      },
    },
  ];
  const edges: Edge[] = [];
  const riskIds = new Set(report.top_risks.map((r) => r.risk_id));
  const riskNodeIds = new Map<string, string>();

  report.top_risks.forEach((risk, i) => {
    const nodeId = `risk-${risk.risk_id}`;
    riskNodeIds.set(risk.risk_id, nodeId);
    nodes.push({
      id: nodeId,
      data: { label: `${risk.risk_type}\n${risk.risk_id}` },
      position: { x: -200 + i * 130, y: 120 },
      style: {
        background: "#fef3c7",
        color: "#92400e",
        borderRadius: 6,
        padding: 8,
        fontSize: 11,
        width: 140,
        whiteSpace: "pre-wrap",
      },
    });
    edges.push({
      id: `e-${companyId}-${nodeId}`,
      source: companyId,
      target: nodeId,
      label: "HAS_RISK",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
      style: { stroke: "#94a3b8" },
    });
  });

  report.evidence_table.forEach((ev, i) => {
    const nodeId = `ev-${ev.evidence_id}`;
    nodes.push({
      id: nodeId,
      data: { label: ev.source_name || ev.evidence_id },
      position: { x: -260 + i * 180, y: 280 },
      style: {
        background: "#e0f2fe",
        color: "#075985",
        borderRadius: 6,
        padding: 6,
        fontSize: 10,
        width: 160,
      },
    });
    for (const rid of ev.related_risk_ids || []) {
      if (riskIds.has(rid) && riskNodeIds.has(rid)) {
        edges.push({
          id: `e-${riskNodeIds.get(rid)}-${nodeId}`,
          source: riskNodeIds.get(rid)!,
          target: nodeId,
          label: "SUPPORTED_BY",
          markerEnd: { type: MarkerType.ArrowClosed, color: "#10b981" },
          style: { stroke: "#10b981" },
        });
      }
    }
  });

  report.graph_insights.forEach((ins, i) => {
    const nodeId = `ins-${ins.insight_id}`;
    nodes.push({
      id: nodeId,
      data: { label: `${ins.affected_entity}\n(insight)` },
      position: { x: -180 + i * 180, y: 440 },
      style: {
        background: "#ede9fe",
        color: "#5b21b6",
        borderRadius: 6,
        padding: 6,
        fontSize: 10,
        width: 160,
        whiteSpace: "pre-wrap",
      },
    });
    if (ins.source_company) {
      edges.push({
        id: `e-${companyId}-${nodeId}`,
        source: companyId,
        target: nodeId,
        label: "AFFECTS",
        markerEnd: { type: MarkerType.ArrowClosed, color: "#8b5cf6" },
        style: { stroke: "#8b5cf6", strokeDasharray: "4 3" },
      });
    }
  });

  return { nodes, edges };
}

export function EvidenceGraph({ report, companyName }: Props) {
  const data = useMemo<GraphData | null>(() => {
    if (!report) return null;
    if (
      report.top_risks.length === 0 &&
      report.evidence_table.length === 0 &&
      report.graph_insights.length === 0
    ) {
      return null;
    }
    return buildGraph(report, companyName ?? null);
  }, [report, companyName]);

  if (!data) {
    return (
      <div className="section empty-state" data-testid="evidence-graph-empty">
        No graph data yet — the workflow has not produced risks, evidence, or
        graph insights.
      </div>
    );
  }

  return (
    <div className="section" data-testid="evidence-graph">
      <h2>Evidence Graph</h2>
      <div className="graph-container" data-testid="evidence-graph-canvas">
        <ReactFlow
          nodes={data.nodes}
          edges={data.edges}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
