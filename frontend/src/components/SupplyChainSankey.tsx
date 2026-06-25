import { useMemo } from "react";
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
}

interface LaidOutLink extends SupplyChainEdgeWire {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  pathD: string;
}

const NODE_WIDTH = 140;
const NODE_GAP_X = 220;
const ROW_HEIGHT = 36;
const ROW_GAP = 8;
const PADDING = 24;

export function SupplyChainSankey({
  payload,
  selectedNodeId,
  onSelectNode,
}: Props) {
  const { nodes, links, width, height, warnings } = useMemo(
    () => layoutSankey(payload),
    [payload],
  );
  return (
    <div className="sc-sankey" data-testid="sc-sankey">
      <div className="sc-sankey-header">
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
      <svg
        width={width}
        height={height}
        data-testid="sc-sankey-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Supply chain Sankey"
      >
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
            strokeWidth={Math.max(1, link.value * 4)}
            opacity={0.5}
            data-testid={`sc-link-${link.edge_id}`}
            onClick={() =>
              onSelectNode(
                link.source_node_id === selectedNodeId
                  ? link.target_node_id
                  : link.source_node_id,
              )
            }
          />
        ))}
        {nodes.map((node) => (
          <g
            key={node.node_id}
            transform={`translate(${node.x}, ${node.y})`}
            data-testid={`sc-node-${node.node_id}`}
            onClick={() => onSelectNode(node.node_id)}
            style={{ cursor: "pointer" }}
          >
            <rect
              width={NODE_WIDTH}
              height={node.height}
              rx={4}
              fill={
                selectedNodeId === node.node_id ? "#10b981" : "#0f172a"
              }
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
      </svg>
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
  const nodes: LaidOutNode[] = [];
  for (const d of depthValues) {
    const layer = byDepth.get(d)!;
    layer.sort((a, b) => a.label.localeCompare(b.label));
    layer.forEach((node, idx) => {
      const x = PADDING + d * NODE_GAP_X;
      const y = PADDING + idx * (ROW_HEIGHT + ROW_GAP);
      nodes.push({ ...node, x, y, height: ROW_HEIGHT });
    });
  }
  const links: LaidOutLink[] = [];
  const nodeIndex = new Map<string, LaidOutNode>();
  for (const n of nodes) {
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
    });
  }
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
