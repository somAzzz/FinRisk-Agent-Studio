import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { pretty, type Link } from "./model";
export default function RelationCanvas({
  edges,
  names,
  focus,
  open,
  expand,
}: {
  edges: (Link & { idx: number })[];
  names: Record<string, string>;
  focus: string;
  open: (idx: number) => void;
  expand: (node: string) => void;
}) {
  const ids = [...new Set(edges.flatMap((e) => [e.subject, e.object]))];
  // Put incoming and outgoing neighbours on either side. For alert paths the
  // alert and the segment both point to the product; do not reverse USES.
  const left = ids.filter(
    (id) =>
      id !== focus && edges.some((e) => e.subject === id && e.object === focus),
  );
  const right = ids.filter(
    (id) =>
      id !== focus && !left.includes(id) && !id.startsWith("Alert reference/"),
  );
  const other = ids.filter(
    (id) => id !== focus && !left.includes(id) && !right.includes(id),
  );
  const mid = Math.max(left.length, right.length, other.length, 1);
  const nodes = ids.map((id) => {
    const col =
      id === focus
        ? null
        : left.includes(id)
          ? left
          : right.includes(id)
            ? right
            : other;
    const row = col ? col.indexOf(id) + (mid - col.length) / 2 : (mid - 1) / 2;
    return {
      id,
      position: {
        x: !col || col === other ? 330 : col === left ? 0 : 660,
        y: col === other ? -115 : row * 108,
      },
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      data: { label: names[id] },
      style: {
        background: id === focus ? "#dbf2ed" : "#fff",
        border: "1px solid #74918f",
        width: 180,
        fontSize: 13,
        color: "#162e35",
      },
      draggable: false,
    };
  });
  return (
    <div className="ar-canvas" aria-label="Focused relationship graph">
      <ReactFlow
        nodes={nodes}
        edges={edges.map((e) => ({
          id: String(e.idx),
          source: e.subject,
          target: e.object,
          label: pretty(e.relation).toLowerCase(),
          type: "straight",
          labelStyle: { fontSize: 12 },
          style: {
            stroke: e.provenance === "model_inference" ? "#a26425" : "#377675",
            strokeDasharray:
              e.provenance === "model_inference" ? "6 4" : undefined,
          },
          markerEnd: { type: MarkerType.ArrowClosed },
        }))}
        fitView
        minZoom={0.2}
        maxZoom={1.8}
        nodesConnectable={false}
        onEdgeClick={(_, e) => open(Number(e.id))}
        onNodeClick={(_, n) => expand(n.id)}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
