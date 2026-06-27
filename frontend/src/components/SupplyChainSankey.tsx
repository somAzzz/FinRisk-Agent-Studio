import { Maximize2, Minus, Move, Plus } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type {
  SupplyChainEdgeWire,
  SupplyChainNodeWire,
  SupplyChainSankeyPayloadWire,
} from "../supply-chain-types";

interface Props {
  payload: SupplyChainSankeyPayloadWire;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}

interface LaidOutNode extends SupplyChainNodeWire {
  x: number;
  y: number;
  height: number;
  riskLevel: RiskLevel;
}

interface LaidOutLink extends SupplyChainEdgeWire {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  pathD: string;
  riskLevel: RiskLevel;
}

type RiskLevel = "stable" | "watch" | "critical";

const NODE_WIDTH = 140;
const NODE_GAP_X = 220;
const ROW_HEIGHT = 36;
const ROW_GAP = 8;
const PARENT_GROUP_GAP = 22;
const PADDING = 24;
const VIEWPORT_WIDTH = 960;
const VIEWPORT_HEIGHT = 560;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2.4;

const RISK_STYLE: Record<
  RiskLevel,
  { label: string; node: string; nodeStroke: string }
> = {
  stable: {
    label: "Low risk",
    node: "#146b63",
    nodeStroke: "#7dd3c7",
  },
  watch: {
    label: "Needs review",
    node: "#9a5b12",
    nodeStroke: "#f5c76b",
  },
  critical: {
    label: "High risk",
    node: "#9f2d25",
    nodeStroke: "#f1a39d",
  },
};

export function SupplyChainSankey({
  payload,
  selectedNodeId,
  onSelectNode,
}: Props) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(
    null,
  );
  const { nodes, links, width, height, warnings } = useMemo(
    () => layoutSankey(payload),
    [payload],
  );
  const viewportWidth = Math.max(VIEWPORT_WIDTH, Math.min(width + 48, 1280));
  const viewportHeight = Math.max(
    360,
    Math.min(Math.max(height + 48, VIEWPORT_HEIGHT), 820),
  );
  const applyZoom = (nextZoom: number) => {
    setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom)));
  };
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };
  return (
    <div className="sc-sankey" data-testid="sc-sankey">
      <div className="sc-sankey-header">
        <div className="sc-sankey-stats">
          <span data-testid="sc-sankey-node-count">
            nodes: {payload.nodes.length}
          </span>
          <span data-testid="sc-sankey-link-count">
            links: {payload.links.length}
          </span>
          <span className="muted">
            Flow width represents relative importance / confidence,
            not procurement spend.
          </span>
        </div>
        <div className="sc-sankey-controls" aria-label="Graph view controls">
          <button
            type="button"
            className="icon-button"
            onClick={() => applyZoom(zoom - 0.15)}
            title="Zoom out"
            aria-label="Zoom out"
            data-testid="sc-zoom-out"
          >
            <Minus size={14} />
          </button>
          <span data-testid="sc-zoom-level">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="icon-button"
            onClick={() => applyZoom(zoom + 0.15)}
            title="Zoom in"
            aria-label="Zoom in"
            data-testid="sc-zoom-in"
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={resetView}
            title="Reset view"
            aria-label="Reset view"
            data-testid="sc-reset-view"
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>
      <div className="sc-risk-legend" aria-label="Risk color legend">
        {(Object.keys(RISK_STYLE) as RiskLevel[]).map((level) => (
          <span key={level}>
            <i style={{ background: RISK_STYLE[level].node }} />
            {RISK_STYLE[level].label}
          </span>
        ))}
      </div>
      <div
        className="sc-sankey-viewport"
        data-testid="sc-sankey-viewport"
        style={{ height: viewportHeight }}
      >
        <div className="sc-pan-hint" aria-hidden="true">
          <Move size={13} /> drag canvas · wheel to zoom
        </div>
        <svg
          width="100%"
          height="100%"
          data-testid="sc-sankey-svg"
          tabIndex={0}
          viewBox={`0 0 ${viewportWidth} ${viewportHeight}`}
          role="img"
          aria-label="Supply chain Sankey"
          onWheel={(event) => {
            event.preventDefault();
            applyZoom(zoom + (event.deltaY > 0 ? -0.08 : 0.08));
          }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.currentTarget.focus();
            event.currentTarget.setPointerCapture(event.pointerId);
            dragRef.current = {
              x: event.clientX,
              y: event.clientY,
              panX: pan.x,
              panY: pan.y,
            };
          }}
          onPointerMove={(event) => {
            const drag = dragRef.current;
            if (!drag) return;
            setPan({
              x: drag.panX + event.clientX - drag.x,
              y: drag.panY + event.clientY - drag.y,
            });
          }}
          onPointerUp={(event) => {
            dragRef.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => {
            dragRef.current = null;
          }}
        >
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            <rect
              className="sc-sankey-canvas"
              data-testid="sc-sankey-canvas"
              x={0}
              y={0}
              width={Math.max(width, viewportWidth)}
              height={Math.max(height, viewportHeight)}
              fill="transparent"
            />
            {links.map((link) => (
              <path
                key={link.edge_id}
                d={link.pathD}
                fill="none"
                stroke={
                  link.source_node_id === selectedNodeId ||
                  link.target_node_id === selectedNodeId
                    ? "#10b981"
                    : "#94a3b8"
                }
                strokeWidth={
                  Math.max(1, link.value * 4)
                  + (link.source_node_id === selectedNodeId ||
                  link.target_node_id === selectedNodeId
                    ? 1
                    : 0)
                }
                opacity={
                  link.source_node_id === selectedNodeId ||
                  link.target_node_id === selectedNodeId
                    ? 0.86
                    : 0.5
                }
                data-risk-level={link.riskLevel}
                data-testid={`sc-link-${link.edge_id}`}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() =>
                  onSelectNode(
                    link.source_node_id === selectedNodeId
                      ? link.target_node_id
                      : link.source_node_id,
                  )
                }
              >
                <title>
                  {`${link.source_node_id} -> ${link.target_node_id} · ${
                    RISK_STYLE[link.riskLevel].label
                  } · confidence ${(link.confidence * 100).toFixed(0)}%`}
                </title>
              </path>
            ))}
            {nodes.map((node) => (
              <g
                key={node.node_id}
                transform={`translate(${node.x}, ${node.y})`}
                data-testid={`sc-node-${node.node_id}`}
                data-risk-level={node.riskLevel}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => onSelectNode(node.node_id)}
                style={{ cursor: "pointer" }}
                aria-label={`${node.label} (${node.node_type})`}
              >
                <title>
                  {node.label} · {node.node_type} ·{" "}
                  {RISK_STYLE[node.riskLevel].label} · confidence{" "}
                  {(node.confidence * 100).toFixed(0)}%
                </title>
                <rect
                  width={NODE_WIDTH}
                  height={node.height}
                  rx={4}
                  fill={RISK_STYLE[node.riskLevel].node}
                  stroke={
                    selectedNodeId === node.node_id
                      ? "#101820"
                      : RISK_STYLE[node.riskLevel].nodeStroke
                  }
                  strokeWidth={selectedNodeId === node.node_id ? 2.4 : 1.1}
                />
                <text
                  x={8}
                  y={20}
                  fontSize={11}
                  fontWeight={600}
                  fill="#f8fafc"
                >
                  {truncate(node.label, 18)}
                </text>
                <text
                  x={8}
                  y={32}
                  fontSize={9}
                  fill="#cbd5f5"
                >
                  {node.node_type} · conf {(node.confidence * 100).toFixed(0)}%
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div>
      <div className="sc-node-index" aria-label="Node full names">
        {nodes.map((node) => (
          <button
            key={node.node_id}
            type="button"
            className={`${selectedNodeId === node.node_id ? "active" : ""} risk-${node.riskLevel}`}
            onClick={() => onSelectNode(node.node_id)}
            title={node.label}
            data-risk-level={node.riskLevel}
          >
            {node.label}
          </button>
        ))}
      </div>
      {warnings.length > 0 ? (
        <ul className="sc-warnings" data-testid="sc-sankey-warnings">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function truncate(text: string, max: number) {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function layoutSankey(payload: SupplyChainSankeyPayloadWire): {
  nodes: LaidOutNode[];
  links: LaidOutLink[];
  width: number;
  height: number;
  warnings: string[];
} {
  // Build a depth map by following "parent_node_id" links, falling
  // back to the v18 "depth" field when no parent is set.
  const nodeById = new Map<string, SupplyChainNodeWire>();
  for (const node of payload.nodes) {
    nodeById.set(node.node_id, node);
  }
  const depthById = new Map<string, number>();
  function depthOf(id: string): number {
    if (depthById.has(id)) {
      return depthById.get(id)!;
    }
    const node = nodeById.get(id);
    if (!node) {
      return 0;
    }
    if (node.parent_node_id && nodeById.has(node.parent_node_id)) {
      const d = depthOf(node.parent_node_id) + 1;
      depthById.set(id, d);
      return d;
    }
    const d = node.depth;
    depthById.set(id, d);
    return d;
  }
  for (const node of payload.nodes) {
    depthOf(node.node_id);
  }
  const byDepth = new Map<number, SupplyChainNodeWire[]>();
  for (const node of payload.nodes) {
    const d = depthById.get(node.node_id) ?? node.depth;
    const arr = byDepth.get(d) ?? [];
    arr.push(node);
    byDepth.set(d, arr);
  }
  const depthValues = [...byDepth.keys()].sort((a, b) => a - b);
  const positionedNodes: Array<Omit<LaidOutNode, "riskLevel">> = [];
  const positionedById = new Map<string, Omit<LaidOutNode, "riskLevel">>();
  for (const d of depthValues) {
    const layer = byDepth.get(d)!;
    layer.sort((a, b) => compareByParentPosition(a, b, positionedById));
    let cursorY = PADDING;
    let previousParent: string | null = null;
    layer.forEach((node) => {
      const parentId = node.parent_node_id ?? null;
      if (previousParent !== null && parentId !== previousParent) {
        cursorY += PARENT_GROUP_GAP;
      }
      const x = PADDING + d * NODE_GAP_X;
      const y = cursorY;
      const positioned = { ...node, x, y, height: ROW_HEIGHT };
      positionedNodes.push(positioned);
      positionedById.set(node.node_id, positioned);
      cursorY += ROW_HEIGHT + ROW_GAP;
      previousParent = parentId;
    });
  }
  const links: LaidOutLink[] = [];
  const nodeIndex = new Map<string, Omit<LaidOutNode, "riskLevel">>();
  for (const n of positionedNodes) {
    nodeIndex.set(n.node_id, n);
  }
  for (const link of payload.links) {
    const src = nodeIndex.get(link.source_node_id);
    const tgt = nodeIndex.get(link.target_node_id);
    if (!src || !tgt) continue;
    const pathD = `M${src.x + NODE_WIDTH} ${src.y + src.height / 2}
      C${(src.x + tgt.x) / 2} ${src.y + src.height / 2},
       ${(src.x + tgt.x) / 2} ${tgt.y + tgt.height / 2},
       ${tgt.x} ${tgt.y + tgt.height / 2}`;
    links.push({
      ...link,
      sourceX: src.x + NODE_WIDTH,
      sourceY: src.y + src.height / 2,
      targetX: tgt.x,
      targetY: tgt.y + tgt.height / 2,
      pathD,
      riskLevel: edgeRiskLevel(link),
    });
  }
  const linksByNode = new Map<string, LaidOutLink[]>();
  for (const link of links) {
    linksByNode.set(link.source_node_id, [
      ...(linksByNode.get(link.source_node_id) ?? []),
      link,
    ]);
    linksByNode.set(link.target_node_id, [
      ...(linksByNode.get(link.target_node_id) ?? []),
      link,
    ]);
  }
  const nodes: LaidOutNode[] = positionedNodes.map((node) => ({
    ...node,
    riskLevel: nodeRiskLevel(node, linksByNode.get(node.node_id) ?? []),
  }));
  const maxX = nodes.length
    ? Math.max(...nodes.map((n) => n.x + NODE_WIDTH))
    : PADDING;
  const maxY = nodes.length
    ? Math.max(...nodes.map((n) => n.y + ROW_HEIGHT))
    : PADDING;
  return {
    nodes,
    links,
    width: maxX + PADDING,
    height: maxY + PADDING,
    warnings: payload.warnings,
  };
}

function compareByParentPosition(
  a: SupplyChainNodeWire,
  b: SupplyChainNodeWire,
  positionedById: Map<string, Omit<LaidOutNode, "riskLevel">>,
): number {
  const parentA = a.parent_node_id
    ? positionedById.get(a.parent_node_id)
    : undefined;
  const parentB = b.parent_node_id
    ? positionedById.get(b.parent_node_id)
    : undefined;
  const parentYDelta = (parentA?.y ?? 0) - (parentB?.y ?? 0);
  if (parentYDelta !== 0) return parentYDelta;
  const parentLabelDelta = (a.parent_node_id ?? "").localeCompare(
    b.parent_node_id ?? "",
  );
  if (parentLabelDelta !== 0) return parentLabelDelta;
  return a.label.localeCompare(b.label);
}

function edgeRiskLevel(edge: SupplyChainEdgeWire): RiskLevel {
  if (edge.confidence < 0.5) return "critical";
  if (edge.relation_type !== "hypothesized" && edge.evidence_ids.length === 0) {
    return "critical";
  }
  if (
    edge.relation_type === "hypothesized"
    || edge.confidence < 0.75
    || edge.evidence_ids.length === 0
  ) {
    return "watch";
  }
  return "stable";
}

function nodeRiskLevel(
  node: Pick<SupplyChainNodeWire, "confidence" | "evidence_ids">,
  incidentLinks: LaidOutLink[],
): RiskLevel {
  if (
    node.confidence < 0.5
    || incidentLinks.some((link) => link.riskLevel === "critical")
  ) {
    return "critical";
  }
  if (
    node.confidence < 0.75
    || incidentLinks.some((link) => link.riskLevel === "watch")
    || (incidentLinks.length > 0 && node.evidence_ids.length === 0)
  ) {
    return "watch";
  }
  return "stable";
}
