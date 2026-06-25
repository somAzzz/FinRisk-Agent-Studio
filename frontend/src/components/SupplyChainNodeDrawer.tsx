import type { SupplyChainNodeWire } from "../supply-chain-types";

interface Props {
  node: SupplyChainNodeWire | null;
  onClose: () => void;
  onExpand: (nodeId: string) => void;
  canExpand: boolean;
}

export function SupplyChainNodeDrawer({
  node,
  onClose,
  onExpand,
  canExpand,
}: Props) {
  if (!node) {
    return (
      <aside
        className="sc-drawer empty"
        data-testid="sc-drawer-empty"
      >
        Click a node to inspect.
      </aside>
    );
  }
  return (
    <aside
      className="sc-drawer"
      data-testid="sc-drawer"
      data-node-id={node.node_id}
    >
      <header>
        <strong>{node.label}</strong>
        <button
          type="button"
          className="ghost"
          onClick={onClose}
          data-testid="sc-drawer-close"
        >
          ×
        </button>
      </header>
      <dl>
        <dt>Type</dt>
        <dd>{node.node_type}</dd>
        <dt>Depth</dt>
        <dd>{node.depth}</dd>
        {node.ticker ? (
          <>
            <dt>Ticker</dt>
            <dd>{node.ticker}</dd>
          </>
        ) : null}
        <dt>Confidence</dt>
        <dd>{(node.confidence * 100).toFixed(0)}%</dd>
        <dt>Evidence</dt>
        <dd>
          {node.evidence_ids.length > 0
            ? node.evidence_ids.join(", ")
            : "(none — see warnings)"}
        </dd>
      </dl>
      {canExpand ? (
        <button
          type="button"
          className="primary"
          data-testid="sc-drawer-expand"
          onClick={() => onExpand(node.node_id)}
        >
          Expand from this node
        </button>
      ) : (
        <div className="muted" data-testid="sc-drawer-no-expand">
          Run the workflow first to enable expansion.
        </div>
      )}
    </aside>
  );
}
