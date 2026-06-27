import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SupplyChainExplorer } from "./SupplyChainExplorer";

const sankeyPayload = {
  run_id: "sc-run-1",
  sankey: {
    nodes: [
      {
        node_id: "company:openai",
        node_type: "company",
        label: "OpenAI",
        normalized_name: "openai",
        depth: 0,
        confidence: 0.95,
        evidence_ids: [],
      },
      {
        node_id: "product:chatgpt",
        node_type: "product",
        label: "ChatGPT",
        normalized_name: "chatgpt",
        depth: 0,
        parent_node_id: "company:openai",
        confidence: 0.95,
        evidence_ids: ["ev-1"],
      },
      {
        node_id: "component:cpu",
        node_type: "component",
        label: "CPU",
        normalized_name: "cpu",
        depth: 2,
        parent_node_id: "service:cloud-compute",
        confidence: 0.42,
        evidence_ids: ["ev-cpu"],
      },
      {
        node_id: "component:high-bandwidth-memory-(hbm3)",
        node_type: "component",
        label: "High-bandwidth memory (HBM3)",
        normalized_name: "high-bandwidth memory (hbm3)",
        depth: 1,
        parent_node_id: "product:chatgpt",
        confidence: 0.85,
        evidence_ids: [],
      },
      {
        node_id: "commodity:rare-earth-minerals",
        node_type: "commodity",
        label: "Rare earth minerals",
        normalized_name: "rare earth minerals",
        depth: 1,
        parent_node_id: "product:chatgpt",
        confidence: 0.78,
        evidence_ids: [],
        metadata: {
          profile: {
            summary:
              "Rare earth minerals are upstream material inputs for permanent magnets and power electronics.",
            key_items: ["Neodymium", "Praseodymium", "Dysprosium"],
            applications: ["Permanent magnets", "Electric motors"],
            risk_factors: ["Export controls", "Separation concentration"],
            comparable_entities: ["Lithium", "Cobalt"],
            generated_by: "llm",
            confidence: 0.81,
          },
        },
      },
      {
        node_id: "company:sk-hynix",
        node_type: "company",
        label: "SK Hynix",
        normalized_name: "sk-hynix",
        depth: 2,
        parent_node_id: "component:high-bandwidth-memory-(hbm3)",
        confidence: 0.85,
        evidence_ids: [],
      },
      {
        node_id: "company:samsung-electronics",
        node_type: "company",
        label: "Samsung Electronics",
        normalized_name: "samsung-electronics",
        depth: 2,
        parent_node_id: "component:high-bandwidth-memory-(hbm3)",
        confidence: 0.75,
        evidence_ids: [],
      },
      {
        node_id: "company:micron",
        node_type: "company",
        label: "Micron",
        normalized_name: "micron",
        depth: 2,
        parent_node_id: "component:high-bandwidth-memory-(hbm3)",
        confidence: 0.7,
        evidence_ids: [],
      },
    ],
    links: [
      {
        edge_id: "e-1",
        source_node_id: "company:openai",
        target_node_id: "product:chatgpt",
        relation_type: "requires",
        value: 1.0,
        value_meaning: "importance",
        confidence: 0.9,
        evidence_ids: ["ev-1"],
      },
      {
        edge_id: "e-2",
        source_node_id: "product:chatgpt",
        target_node_id: "component:cpu",
        relation_type: "hypothesized",
        value: 0.8,
        value_meaning: "importance",
        confidence: 0.42,
        evidence_ids: [],
      },
    ],
    evidence: [],
    warnings: [],
  },
};

const startMock = vi.fn().mockResolvedValue({ run_id: "sc-run-1", status: "completed" });
const sankeyMock = vi.fn().mockResolvedValue(sankeyPayload);
const statusMock = vi.fn().mockResolvedValue({
  run_id: "sc-run-1",
  status: "completed",
  request: {
    company_name: "OpenAI",
    product_name: "ChatGPT",
    demo_mode: false,
    cached_mode: false,
    llm_config: {
      provider: "deepseek",
      base_url: "https://api.deepseek.com",
      model: "deepseek-v4-flash",
    },
  },
  current_step: null,
  node_count: 3,
  link_count: 1,
  evidence_count: 0,
  evaluation: null,
  trace: [],
  warnings: [],
  fallback_events: [],
});
const expandMock = vi.fn().mockResolvedValue({ run_id: "sc-run-child", status: "queued" });

vi.mock("../api", () => ({
  api: {
    startSupplyChain: (...args: unknown[]) => startMock(...args),
    getSupplyChainStatus: (...args: unknown[]) => statusMock(...args),
    getSupplyChainSankey: (...args: unknown[]) => sankeyMock(...args),
    expandSupplyChain: (...args: unknown[]) => expandMock(...args),
  },
  FinRiskApiError: class extends Error {
    status: number;
    body: unknown;
    constructor(message: string, status: number, body: unknown) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

describe("SupplyChainExplorer", () => {
  beforeEach(() => {
    startMock.mockClear();
    sankeyMock.mockClear();
    statusMock.mockClear();
    expandMock.mockClear();
  });

  it("renders the default form with OpenAI / ChatGPT", () => {
    render(<SupplyChainExplorer />);
    expect(screen.getByTestId("sc-company-input")).toHaveValue("OpenAI");
    expect(screen.getByTestId("sc-product-input")).toHaveValue("ChatGPT");
    expect(screen.queryByTestId("sc-demo-mode")).not.toBeInTheDocument();
    expect(screen.getByTestId("llm-provider-select")).toHaveValue("deepseek");
  });

  it("clicking Run calls the API and renders the Sankey", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    expect(startMock).toHaveBeenCalled();
    expect(startMock).toHaveBeenCalledWith(
      expect.objectContaining({
        demo_mode: false,
        cached_mode: false,
        llm_config: expect.objectContaining({ provider: "deepseek" }),
      }),
    );
    expect(sankeyMock).toHaveBeenCalledWith("sc-run-1");
  });

  it("submits a deeper max depth selection", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.change(screen.getByTestId("sc-depth-input"), {
      target: { value: "8" },
    });
    expect(screen.getByTestId("sc-depth-value").textContent).toBe("8");
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.objectContaining({
          max_depth: 8,
        }),
      );
    });
  });

  it("submits selected LLM provider", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.change(screen.getByTestId("llm-provider-select"), {
      target: { value: "deepseek" },
    });
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.objectContaining({
          llm_config: expect.objectContaining({
            provider: "deepseek",
            base_url: "https://api.deepseek.com",
            model: "deepseek-v4-flash",
          }),
        }),
      );
    });
  });

  it("clicking a node opens the drawer", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("sc-node-component:cpu"));
    expect(screen.getByTestId("sc-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("sc-drawer").getAttribute("data-node-id")).toBe(
      "component:cpu",
    );
  });

  it("shows company scope and comparable suppliers for selected company nodes", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("sc-node-company:sk-hynix"));
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Memory semiconductor supplier",
    );
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Samsung Electronics",
    );
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Micron",
    );
  });

  it("shows node intelligence for non-company material nodes", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("sc-node-commodity:rare-earth-minerals"));
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Rare earth minerals are upstream material inputs",
    );
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Neodymium",
    );
    expect(screen.getByTestId("sc-node-profile").textContent).toContain(
      "Export controls",
    );
  });

  it("renders graph viewport controls and node full-name affordances", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey-viewport")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sc-zoom-in")).toBeInTheDocument();
    expect(screen.getByTestId("sc-zoom-out")).toBeInTheDocument();
    expect(screen.getByTestId("sc-sankey-canvas")).toHaveClass(
      "sc-sankey-canvas",
    );
    expect(screen.getAllByTitle("ChatGPT").length).toBeGreaterThan(0);
  });

  it("marks graph nodes and links with risk levels", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sc-node-component:cpu")).toHaveAttribute(
      "data-risk-level",
      "critical",
    );
    expect(screen.getByTestId("sc-link-e-2")).toHaveAttribute(
      "data-risk-level",
      "critical",
    );
  });

  it("expands from a selected node in live mode", async () => {
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-sankey")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("sc-node-component:cpu"));
    fireEvent.click(screen.getByTestId("sc-drawer-expand"));
    await waitFor(() => {
      expect(expandMock).toHaveBeenCalledWith(
        expect.objectContaining({
          parent_run_id: "sc-run-1",
          node_id: "component:cpu",
          demo_mode: false,
          cached_mode: false,
        }),
      );
    });
  });

  it("shows review reasons when the run needs review", async () => {
    const reviewStatus = {
      run_id: "sc-run-1",
      status: "needs_review",
      request: {
        company_name: "OpenAI",
        product_name: "ChatGPT",
        demo_mode: false,
        cached_mode: false,
        llm_config: {
          provider: "deepseek",
          base_url: "https://api.deepseek.com",
          model: "deepseek-v4-flash",
        },
      },
      current_step: null,
      node_count: 2,
      link_count: 0,
      evidence_count: 0,
      evaluation: {
        final_status: "needs_review",
        human_review_required: true,
        unsupported_edges: [],
        low_confidence_edges: [],
        source_diversity_score: 0,
      },
      trace: [],
      warnings: ["graph contains no confirmed suppliers"],
      fallback_events: [],
    };
    statusMock.mockResolvedValueOnce(reviewStatus).mockResolvedValueOnce(reviewStatus);
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-review-summary").textContent).toContain(
        "graph contains no confirmed suppliers",
      );
    });
  });

  it("API error renders an error banner", async () => {
    startMock.mockRejectedValueOnce(new Error("boom"));
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-error").textContent).toContain("boom");
    });
  });
});
