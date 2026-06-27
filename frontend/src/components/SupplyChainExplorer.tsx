import { useEffect, useMemo, useRef, useState } from "react";
import type {
  SupplyChainExploreRequestWire,
  SupplyChainSankeyPayloadWire,
  SupplyChainStatusResponseWire,
} from "../supply-chain-types";
import { api, FinRiskApiError } from "../api";
import { LLMProviderSelector } from "./LLMProviderSelector";
import { SupplyChainSankey } from "./SupplyChainSankey";
import { SupplyChainNodeDrawer } from "./SupplyChainNodeDrawer";

interface Props {
  initialCompany?: string;
  initialProduct?: string;
  onProgress?: (status: SupplyChainStatusResponseWire | null) => void;
  selectedRunId?: string | null;
}

const DEFAULT_REQUEST: SupplyChainExploreRequestWire = {
  company_name: "OpenAI",
  product_name: "ChatGPT",
  max_depth: 3,
  max_suppliers_per_node: 5,
  demo_mode: false,
  cached_mode: false,
  llm_config: {
    provider: "deepseek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
  },
};

const MIN_SUPPLY_CHAIN_DEPTH = 1;
const MAX_SUPPLY_CHAIN_DEPTH = 10;
const TERMINAL_STATUSES = new Set(["completed", "failed", "needs_review"]);

function formatApiError(err: unknown): string {
  if (err instanceof FinRiskApiError) {
    const detail = (err.body as { detail?: unknown } | null)?.detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (!item || typeof item !== "object") return String(item);
          const issue = item as Record<string, unknown>;
          const loc = Array.isArray(issue.loc) ? issue.loc.join(".") : "request";
          return `${loc}: ${String(issue.msg ?? "invalid value")}`;
        })
        .join("; ");
      return `API ${err.status}: ${messages}`;
    }
    if (detail) return `API ${err.status}: ${String(detail)}`;
    return `API ${err.status}: ${err.message}`;
  }
  return (err as Error).message;
}

export function SupplyChainExplorer({
  initialCompany = "OpenAI",
  initialProduct = "ChatGPT",
  onProgress,
  selectedRunId,
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
  const pollRef = useRef<number | null>(null);
  requestRef.current = request;

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  const refreshRun = async (
    targetRunId: string,
    sankeyRunId = targetRunId,
  ): Promise<SupplyChainStatusResponseWire | null> => {
    const status = await api.getSupplyChainStatus(targetRunId);
    onProgress?.(status);
    if (TERMINAL_STATUSES.has(status.status)) {
      stopPolling();
      const sankeyResp = await api.getSupplyChainSankey(sankeyRunId);
      const finalStatus = await api.getSupplyChainStatus(targetRunId);
      onProgress?.(finalStatus);
      setSankey(sankeyResp.sankey);
      setBusy(false);
      return finalStatus;
    }
    return status;
  };

  const startPolling = (targetRunId: string, sankeyRunId = targetRunId) => {
    stopPolling();
    void refreshRun(targetRunId, sankeyRunId).catch((err) => {
      setError(formatApiError(err));
      setBusy(false);
      stopPolling();
    });
    pollRef.current = window.setInterval(() => {
      void refreshRun(targetRunId, sankeyRunId).catch((err) => {
        setError(formatApiError(err));
        setBusy(false);
        stopPolling();
      });
    }, 1500);
  };

  useEffect(() => {
    if (!selectedRunId || selectedRunId === runId) return;
    stopPolling();
    setBusy(true);
    setError(null);
    setRunId(selectedRunId);
    void refreshRun(selectedRunId)
      .catch((err) => setError(formatApiError(err)))
      .finally(() => setBusy(false));
  }, [selectedRunId]);

  const run = async (req: SupplyChainExploreRequestWire) => {
    setBusy(true);
    setError(null);
    onProgress?.(null);
    try {
      const resp = await api.startSupplyChain(req);
      setRunId(resp.run_id);
      onProgress?.({
        run_id: resp.run_id,
        status: resp.status,
        current_step: null,
        node_count: 0,
        link_count: 0,
        evidence_count: 0,
        evaluation: null,
        trace: [],
        warnings: [],
        fallback_events: [],
      });
      startPolling(resp.run_id);
    } catch (err) {
      setError(formatApiError(err));
      setBusy(false);
    }
  };

  const expand = async (nodeId: string) => {
    if (!runId) return;
    setBusy(true);
    setError(null);
    const currentRequest = requestRef.current;
    try {
      const resp = await api.expandSupplyChain({
        parent_run_id: runId,
        node_id: nodeId,
        product_name: nodeId.split(":").slice(-1)[0],
        max_depth: 2,
        demo_mode: currentRequest.demo_mode ?? false,
        cached_mode: currentRequest.cached_mode ?? false,
        llm_config: currentRequest.llm_config,
      });
      onProgress?.({
        run_id: resp.run_id,
        status: resp.status,
        current_step: null,
        node_count: sankey?.nodes.length ?? 0,
        link_count: sankey?.links.length ?? 0,
        evidence_count: sankey?.evidence.length ?? 0,
        evaluation: null,
        trace: [],
        warnings: [],
        fallback_events: [],
      });
      startPolling(resp.run_id, runId);
    } catch (err) {
      setError(formatApiError(err));
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
            required
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
            required
            onChange={(e) =>
              setRequest((r) => ({ ...r, product_name: e.target.value }))
            }
          />
        </div>
        <div className="row">
          <label htmlFor="sc-depth">Max depth</label>
          <div className="range-pair compact">
            <div className="range-value" data-testid="sc-depth-value">
              {request.max_depth ?? 3}
            </div>
            <input
              id="sc-depth"
              type="range"
              min={MIN_SUPPLY_CHAIN_DEPTH}
              max={MAX_SUPPLY_CHAIN_DEPTH}
              step={1}
              value={request.max_depth ?? 3}
              onChange={(e) =>
                setRequest((r) => ({
                  ...r,
                  max_depth: Number(e.target.value) || 3,
                }))
              }
              data-testid="sc-depth-input"
            />
            <div className="range-scale" aria-hidden="true">
              <span>{MIN_SUPPLY_CHAIN_DEPTH}</span>
              <span>{MAX_SUPPLY_CHAIN_DEPTH}</span>
            </div>
          </div>
        </div>
        <div className="row-checkbox">
          <input
            id="sc-demo"
            type="checkbox"
            data-testid="sc-demo-mode"
            checked={request.demo_mode ?? false}
            onChange={(e) =>
              setRequest((r) => ({
                ...r,
                demo_mode: e.target.checked,
                cached_mode: e.target.checked,
              }))
            }
          />
          <label htmlFor="sc-demo">Demo mode (offline fixture)</label>
        </div>
        <LLMProviderSelector
          value={request.llm_config ?? DEFAULT_REQUEST.llm_config!}
          onChange={(next) =>
            setRequest((r) => ({ ...r, llm_config: next }))
          }
        />
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
