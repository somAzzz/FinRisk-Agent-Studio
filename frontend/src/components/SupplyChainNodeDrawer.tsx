import type {
  SupplyChainNodeProfileWire,
  SupplyChainNodeWire,
  SupplyChainSankeyPayloadWire,
} from "../supply-chain-types";

interface Props {
  node: SupplyChainNodeWire | null;
  payload?: SupplyChainSankeyPayloadWire | null;
  onClose: () => void;
  onExpand: (nodeId: string) => void;
  canExpand: boolean;
}

export function SupplyChainNodeDrawer({
  node,
  payload,
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
  const nodeProfile = nodeProfileFor(node, payload);
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
      {nodeProfile ? (
        <section
          className="sc-node-profile"
          data-testid="sc-node-profile"
        >
          <h3>Node intelligence</h3>
          <p>{nodeProfile.summary}</p>
          <ProfilePills title="Key items" values={nodeProfile.key_items} />
          <ProfilePills title="Applications" values={nodeProfile.applications} />
          <ProfilePills
            title="Risk factors"
            values={nodeProfile.risk_factors}
          />
          <ProfilePills
            title={
              node.node_type === "company"
                ? "Comparable suppliers"
                : "Related entities"
            }
            values={nodeProfile.comparable_entities}
          />
          <div className="sc-node-profile-foot">
            {nodeProfile.generated_by ? nodeProfile.generated_by : "profile"}
            {typeof nodeProfile.confidence === "number"
              ? ` · ${(nodeProfile.confidence * 100).toFixed(0)}%`
              : ""}
          </div>
        </section>
      ) : null}
    </aside>
  );
}

function ProfilePills({
  title,
  values,
}: {
  title: string;
  values?: string[];
}) {
  const clean = (values ?? []).filter(Boolean);
  if (!clean.length) return null;
  return (
    <>
      <h4>{title}</h4>
      <div className="sc-profile-pill-list">
        {clean.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
    </>
  );
}

function nodeProfileFor(
  node: SupplyChainNodeWire,
  payload?: SupplyChainSankeyPayloadWire | null,
): SupplyChainNodeProfileWire | null {
  const metadataProfile = coerceMetadataProfile(node.metadata?.profile);
  if (metadataProfile) return metadataProfile;
  if (node.node_type === "company") return companyProfileFor(node, payload);
  return fallbackNodeProfileFor(node, payload);
}

function coerceMetadataProfile(
  value: unknown,
): SupplyChainNodeProfileWire | null {
  if (!value || typeof value !== "object") return null;
  const profile = value as Record<string, unknown>;
  const summary = typeof profile.summary === "string" ? profile.summary : "";
  if (!summary.trim()) return null;
  return {
    summary,
    key_items: stringList(profile.key_items),
    applications: stringList(profile.applications),
    risk_factors: stringList(profile.risk_factors),
    comparable_entities: stringList(profile.comparable_entities),
    generated_by:
      typeof profile.generated_by === "string" ? profile.generated_by : undefined,
    confidence:
      typeof profile.confidence === "number" ? profile.confidence : undefined,
  };
}

interface CompanyProfile {
  summary: string;
  comparable_entities: string[];
  applications?: string[];
  risk_factors?: string[];
  key_items?: string[];
  generated_by?: string;
  confidence?: number;
}

const KNOWN_COMPANY_PROFILES: Record<string, CompanyProfile> = {
  "sk-hynix": {
    summary:
      "Memory semiconductor supplier focused on DRAM, NAND flash, and high-bandwidth memory used in AI accelerators.",
    comparable_entities: [
      "Samsung Electronics",
      "Micron",
      "Kioxia",
      "Western Digital",
    ],
  },
  samsung: {
    summary:
      "Diversified electronics and semiconductor manufacturer with DRAM, NAND, HBM, foundry, display, and device businesses.",
    comparable_entities: ["SK Hynix", "Micron", "TSMC", "Kioxia"],
  },
  micron: {
    summary:
      "US memory manufacturer supplying DRAM, NAND, and HBM products for data center, client, automotive, and industrial markets.",
    comparable_entities: [
      "SK Hynix",
      "Samsung Electronics",
      "Kioxia",
      "Western Digital",
    ],
  },
  nvidia: {
    summary:
      "Accelerated computing company supplying GPUs, AI accelerators, networking, and software platforms for data centers.",
    comparable_entities: ["AMD", "Intel", "Broadcom", "Marvell"],
  },
  amd: {
    summary:
      "Semiconductor company supplying CPUs, GPUs, adaptive SoCs, and data-center accelerators.",
    comparable_entities: ["Intel", "NVIDIA", "Qualcomm", "Marvell"],
  },
  intel: {
    summary:
      "Semiconductor company focused on CPUs, data-center platforms, networking silicon, and foundry services.",
    comparable_entities: ["AMD", "NVIDIA", "TSMC", "Samsung Electronics"],
  },
  tsmc: {
    summary:
      "Pure-play semiconductor foundry manufacturing advanced logic chips for fabless and integrated device customers.",
    comparable_entities: [
      "Samsung Foundry",
      "Intel Foundry",
      "GlobalFoundries",
      "UMC",
    ],
  },
  "microsoft-azure": {
    summary:
      "Cloud infrastructure platform providing compute, storage, networking, AI services, and managed data services.",
    comparable_entities: [
      "Amazon Web Services",
      "Google Cloud",
      "Oracle Cloud",
      "CoreWeave",
    ],
  },
  microsoft: {
    summary:
      "Software, cloud, productivity, and AI platform company. Azure is its cloud infrastructure business.",
    comparable_entities: [
      "Amazon Web Services",
      "Google Cloud",
      "Oracle Cloud",
      "Salesforce",
    ],
  },
  "amazon-web-services": {
    summary:
      "Cloud infrastructure platform providing compute, storage, networking, databases, AI services, and managed platforms.",
    comparable_entities: [
      "Microsoft Azure",
      "Google Cloud",
      "Oracle Cloud",
      "CoreWeave",
    ],
  },
  oracle: {
    summary:
      "Enterprise software, database, and cloud infrastructure provider with OCI data-center services.",
    comparable_entities: [
      "Microsoft Azure",
      "Amazon Web Services",
      "Google Cloud",
      "IBM Cloud",
    ],
  },
  coreweave: {
    summary:
      "Specialized cloud provider focused on GPU compute capacity for AI training, inference, rendering, and batch workloads.",
    comparable_entities: ["Lambda", "Crusoe", "Microsoft Azure", "Amazon Web Services"],
  },
};

function companyProfileFor(
  node: SupplyChainNodeWire,
  payload?: SupplyChainSankeyPayloadWire | null,
): SupplyChainNodeProfileWire {
  const key = normalizeCompanyKey(node.label);
  const known = KNOWN_COMPANY_PROFILES[key];
  const graphPeers = peersFromGraph(node, payload);
  if (known) {
    return {
      summary: known.summary,
      key_items: known.key_items ?? [],
      applications: known.applications ?? ["Supply-chain dependency"],
      risk_factors: known.risk_factors ?? [
        "Evidence strength and concentration require review",
      ],
      comparable_entities: mergeUnique([
        ...known.comparable_entities,
        ...graphPeers,
      ]).filter((peer) => normalizeCompanyKey(peer) !== key),
      generated_by: known.generated_by ?? "taxonomy",
      confidence: known.confidence ?? node.confidence,
    };
  }
  return {
    summary:
      "Company node identified as a supplier, infrastructure provider, manufacturer, or dependency candidate in this supply-chain graph.",
    key_items: [],
    applications: ["Supply-chain dependency"],
    risk_factors: ["Evidence strength and concentration require review"],
    comparable_entities: graphPeers,
    generated_by: "taxonomy",
    confidence: node.confidence,
  };
}

function fallbackNodeProfileFor(
  node: SupplyChainNodeWire,
  payload?: SupplyChainSankeyPayloadWire | null,
): SupplyChainNodeProfileWire {
  const children = payload?.nodes
    .filter((candidate) => candidate.parent_node_id === node.node_id)
    .map((candidate) => candidate.label) ?? [];
  return {
    summary: `${node.label} is a ${node.node_type} dependency in this supply-chain graph.`,
    key_items: children.slice(0, 6),
    applications: ["Product delivery", "Operational resilience"],
    risk_factors: ["Evidence may require review"],
    comparable_entities: peersFromGraph(node, payload),
    generated_by: "fallback",
    confidence: node.confidence,
  };
}

function peersFromGraph(
  node: SupplyChainNodeWire,
  payload?: SupplyChainSankeyPayloadWire | null,
): string[] {
  if (!payload) return [];
  const peers = payload.nodes.filter(
    (candidate) =>
      candidate.node_type === "company"
      && candidate.node_id !== node.node_id
      && candidate.parent_node_id === node.parent_node_id,
  );
  return peers.map((peer) => peer.label);
}

function mergeUnique(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const key = normalizeCompanyKey(value);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
      (item): item is string => typeof item === "string" && Boolean(item.trim()),
    )
    : [];
}

function normalizeCompanyKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/electronics|corporation|corp\.?|inc\.?|ltd\.?|co\.?/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
