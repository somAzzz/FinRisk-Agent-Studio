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
        confidence: 0.9,
        evidence_ids: ["ev-cpu"],
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
    ],
    evidence: [],
    warnings: [],
  },
};

const startMock = vi.fn().mockResolvedValue({ run_id: "sc-run-1", status: "completed" });
const sankeyMock = vi.fn().mockResolvedValue(sankeyPayload);
const statusMock = vi.fn().mockResolvedValue({ run_id: "sc-run-1", status: "completed" });
const expandMock = vi.fn().mockResolvedValue({ run_id: "sc-run-1", status: "completed" });

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
    expect(screen.getByTestId("sc-demo-mode")).not.toBeChecked();
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
            model: "deepseek-chat",
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

  it("API error renders an error banner", async () => {
    startMock.mockRejectedValueOnce(new Error("boom"));
    render(<SupplyChainExplorer />);
    fireEvent.click(screen.getByTestId("sc-run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("sc-error").textContent).toContain("boom");
    });
  });
});
