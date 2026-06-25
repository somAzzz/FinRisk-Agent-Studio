import { useMemo, useRef, useState } from "react";
import type {
  SupplyChainExploreRequestWire,
  SupplyChainSankeyPayloadWire,
} from "../supply-chain-types";
import { api } from "../api";
import { SupplyChainSankey } from "./SupplyChainSankey";
import { SupplyChainNodeDrawer } from "./SupplyChainNodeDrawer";

interface Props {
  initialCompany?: string;
  initialProduct?: string;
}

const DEFAULT_REQUEST: SupplyChainExploreRequestWire = {
  company_name: "OpenAI",
  product_name: "ChatGPT",
  max_depth: 3,
  max_suppliers_per_node: 5,
  demo_mode: true,
  cached_mode: true,
};

export function SupplyChainExplorer({
  initialCompany = "OpenAI",
  initialProduct = "ChatGPT",
}: Props) {
  const [request, setRequest] = useState<SupplyChainExploreRequestWire>({
    ...DEFAULT_REQUEST,
    company_name: initialCompany,
    product_name: initialProduct,
  });
  const [sankey, setSankey] = useState<SupplyChainSankeyPayloadWire | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requestRef = useRef(request);
  requestRef.current = request;

  const run = async (req: SupplyChainExploreRequestWire) => {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.startSupplyChain(req);
      const sankeyResp = await api.getSupplyChainSankey(resp.run_id);
      setSankey(sankeyResp.sankey);
      setRunId(resp.run_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const expand = async (nodeId: string) => {
    if (!runId) return;
    setBusy(true);
    setError(null);
    try {
      await api.expandSupplyChain({
        parent_run_id: runId,
        node_id: nodeId,
        product_name: nodeId.split(":").slice(-1)[0],
        max_depth: 2,
        demo_mode: true,
        cached_mode: true,
      });
      const sankeyResp = await api.getSupplyChainSankey(runId);
      setSankey(sankeyResp.sankey);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const selectedNode = useMemo(() => {
    if (!sankey || !selectedNodeId) return null;
    return sankey.nodes.find((n) => n.node_id === selectedNodeId) ?? null;
  }, [sankey, selectedNodeId]);

  return (
    <div className="sc-explorer" data-testid="supply-chain-explorer">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(request);
        }}
      >
        <h2>Supply Chain Explorer</h2>
        <div className="row">
          <label htmlFor="sc-company">Company</label>
          <input
            id="sc-company"
            data-testid="sc-company-input"
            value={request.company_name ?? ""}
            onChange={(e) =>
              setRequest((r) => ({ ...r, company_name: e.target.value }))
            }
          />
        </div>
        <div className="row">
          <label htmlFor="sc-product">Product</label>
          <input
            id="sc-product"
            data-testid="sc-product-input"
            value={request.product_name}
            onChange={(e) =>
              setRequest((r) => ({ ...r, product_name: e.target.value }))
            }
          />
        </div>
        <div className="row">
          <label htmlFor="sc-depth">Max depth</label>
          <input
            id="sc-depth"
            type="number"
            min={1}
            max={5}
            value={request.max_depth ?? 3}
            onChange={(e) =>
              setRequest((r) => ({
                ...r,
                max_depth: Number(e.target.value) || 3,
              }))
            }
          />
        </div>
        <div className="row-checkbox">
          <input
            id="sc-demo"
            type="checkbox"
            data-testid="sc-demo-mode"
            checked={request.demo_mode ?? true}
            onChange={(e) =>
              setRequest((r) => ({ ...r, demo_mode: e.target.checked }))
            }
          />
          <label htmlFor="sc-demo">Demo mode (offline fixture)</label>
        </div>
        <button
          type="submit"
          className="primary"
          disabled={busy}
          data-testid="sc-run-button"
        >
          {busy ? "Running..." : "Run Supply Chain"}
        </button>
        {error ? (
          <div className="error-banner" data-testid="sc-error">
            {error}
          </div>
        ) : null}
      </form>

      <div className="sc-body">
        {sankey ? (
          <SupplyChainSankey
            payload={sankey}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        ) : (
          <div
            className="empty-state"
            data-testid="sc-empty-state"
          >
            Click <strong>Run Supply Chain</strong> to explore
            {" "}
            <em>{request.product_name}</em>.
          </div>
        )}
        <SupplyChainNodeDrawer
          node={selectedNode}
          onClose={() => setSelectedNodeId(null)}
          onExpand={expand}
          canExpand={Boolean(runId)}
        />
      </div>
    </div>
  );
}
