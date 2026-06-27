// v18 Supply Chain types — kept in a separate file so the
// v15/v17 React app shell does not need to import them at
// startup. The names mirror src/supply_chain/models.py.

export type SupplyChainNodeType =
  | "company"
  | "product"
  | "component"
  | "service"
  | "commodity"
  | "infrastructure"
  | "energy"
  | "region"
  | "unknown";

export interface SupplyChainNodeWire {
  node_id: string;
  node_type: SupplyChainNodeType;
  label: string;
  normalized_name: string;
  ticker?: string | null;
  depth: number;
  parent_node_id?: string | null;
  confidence: number;
  evidence_ids: string[];
  metadata?: Record<string, unknown>;
}

export interface SupplyChainNodeProfileWire {
  summary: string;
  key_items?: string[];
  applications?: string[];
  risk_factors?: string[];
  comparable_entities?: string[];
  generated_by?: string;
  confidence?: number;
}

export type SupplyChainRelationType =
  | "requires"
  | "supplied_by"
  | "depends_on"
  | "manufactured_by"
  | "hosted_on"
  | "powered_by"
  | "enabled_by"
  | "hypothesized";

export type SupplyChainEdgeValueMeaning =
  | "importance"
  | "confidence_weight"
  | "estimated_spend"
  | "capacity_dependency";

export interface SupplyChainEdgeWire {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: SupplyChainRelationType;
  value: number;
  value_meaning: SupplyChainEdgeValueMeaning;
  confidence: number;
  evidence_ids: string[];
  metadata?: Record<string, unknown>;
}

export interface SupplyChainEvidenceWire {
  evidence_id: string;
  source_type: string;
  source_name?: string | null;
  url?: string | null;
  title?: string | null;
  quote: string;
  summary: string;
  retrieved_at: string;
  published_at?: string | null;
  confidence: number;
  metadata?: Record<string, unknown>;
}

export interface SupplyChainSankeyPayloadWire {
  nodes: SupplyChainNodeWire[];
  links: SupplyChainEdgeWire[];
  evidence: SupplyChainEvidenceWire[];
  warnings: string[];
}

export interface SupplyChainExploreRequestWire {
  company_name?: string | null;
  ticker?: string | null;
  product_name: string;
  max_depth?: number;
  max_suppliers_per_node?: number;
  focus_regions?: string[];
  include_private_companies?: boolean;
  demo_mode?: boolean;
  cached_mode?: boolean;
  llm_config?: LLMRunConfig;
}

export interface SupplyChainExpandRequestWire {
  parent_run_id: string;
  node_id: string;
  product_name?: string | null;
  seed_companies?: string[];
  max_depth?: number;
  max_suppliers_per_node?: number;
  demo_mode?: boolean;
  cached_mode?: boolean;
  llm_config?: LLMRunConfig;
}

export interface SupplyChainExploreResponseWire {
  run_id: string;
  status: string;
  sankey_url?: string | null;
  error?: string | null;
}

export interface SupplyChainStatusResponseWire {
  run_id: string;
  status: string;
  request: SupplyChainExploreRequestWire;
  current_step: string | null;
  node_count: number;
  link_count: number;
  evidence_count: number;
  parent_run_id?: string | null;
  expanded_from_node_id?: string | null;
  evaluation: {
    final_status: "pass" | "needs_review" | "fail";
    schema_valid?: boolean;
    graph_connected?: boolean;
    acyclic_for_sankey?: boolean;
    confirmed_edges_have_evidence?: boolean;
    human_review_required: boolean;
    unsupported_edges: string[];
    low_confidence_edges?: string[];
    source_diversity_score?: number;
  } | null;
  trace: Array<Record<string, unknown>>;
  warnings: string[];
  fallback_events: string[];
}
import type { LLMRunConfig } from "./types";
