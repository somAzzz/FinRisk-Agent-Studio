// StepOutputInspector — tabbed inspector for one workflow step's
// per-step observability data (added 2026-06-25). Each tab renders a
// list of records from the matching /workflows/{id}/* endpoint:
//
//   * Chunks   — every ChunkValidation row
//   * LLM Log  — every LLMCall row (chat history + token usage)
//   * Section  — SectionLocation rows (where Item 1A was found)
//   * Lifecycle — RiskLifecycleAnnotation rows (one per risk)
//
// The lists are rendered as collapsible <details> blocks so the page
// stays compact when a run has dozens of chunks. The component reads
// the run_id + step_name from props and fetches lazily on first use.

import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  ChunkValidation,
  LLMCall,
  RiskLifecycleAnnotation,
  SectionLocation,
} from "../types";
import { LifecycleBadge } from "./LifecycleBadge";

interface Props {
  runId: string;
  stepName: string;
  // Pre-loaded data; the parent (EvaluationTab) fetches the whole
  // trace once and passes the relevant slices down. This avoids
  // per-step refetch storms.
  llmCalls: LLMCall[];
  chunkValidations: ChunkValidation[];
  sectionLocations: SectionLocation[];
  riskLifecycles: RiskLifecycleAnnotation[];
}

type Tab = "chunks" | "llm" | "section" | "lifecycle";

const TAB_LABELS: Record<Tab, string> = {
  chunks: "Chunks",
  llm: "LLM Log",
  section: "Section Match",
  lifecycle: "Lifecycle",
};

export function StepOutputInspector({
  runId: _runId,
  stepName,
  llmCalls,
  chunkValidations,
  sectionLocations,
  riskLifecycles,
}: Props) {
  const [tab, setTab] = useState<Tab>("chunks");
  const [data, setData] = useState<Props>({
    runId: _runId,
    stepName,
    llmCalls,
    chunkValidations,
    sectionLocations,
    riskLifecycles,
  });

  // Lazily load missing data from the dedicated endpoints so the
  // parent does not need to pass every slice eagerly.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      const updates: Partial<Props> = {};
      if (llmCalls.length === 0) {
        const r = await api.getLLMLog(_runId);
        updates.llmCalls = r.llm_log.filter((c) => c.step_name === stepName);
      }
      if (chunkValidations.length === 0) {
        const r = await api.getChunks(_runId);
        updates.chunkValidations = r.chunk_validations.filter(
          (c) => c.section_name === "section_1a",
        );
      }
      if (sectionLocations.length === 0) {
        const r = await api.getSections(_runId);
        updates.sectionLocations = r.section_locations;
      }
      if (riskLifecycles.length === 0) {
        const r = await api.getLifecycles(_runId);
        updates.riskLifecycles = r.risk_lifecycles;
      }
      if (!cancelled) {
        setData((prev) => ({ ...prev, ...updates }));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [_runId, stepName, llmCalls.length, chunkValidations.length, sectionLocations.length, riskLifecycles.length]);

  const counts: Record<Tab, number> = {
    chunks: data.chunkValidations.length,
    llm: data.llmCalls.length,
    section: data.sectionLocations.length,
    lifecycle: data.riskLifecycles.length,
  };

  return (
    <div className="step-inspector" data-testid={`step-inspector-${stepName}`}>
      <div role="tablist" className="step-inspector-tabs">
        {(Object.keys(TAB_LABELS) as Tab[]).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`step-inspector-tab ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            {TAB_LABELS[id]} ({counts[id]})
          </button>
        ))}
      </div>
      <div role="tabpanel" className="step-inspector-panel">
        {tab === "chunks" && <ChunkList chunks={data.chunkValidations} />}
        {tab === "llm" && <LLMCallList calls={data.llmCalls} />}
        {tab === "section" && (
          <SectionList sections={data.sectionLocations} />
        )}
        {tab === "lifecycle" && (
          <LifecycleList rows={data.riskLifecycles} />
        )}
      </div>
    </div>
  );
}

function ChunkList({ chunks }: { chunks: ChunkValidation[] }) {
  if (chunks.length === 0) {
    return <Empty msg="No chunk validations recorded for this step." />;
  }
  return (
    <ul className="step-inspector-list">
      {chunks.map((c) => (
        <li key={c.chunk_id} className="step-inspector-item">
          <details>
            <summary>
              <span className={`pill ${c.ok ? "ok" : "fail"}`}>
                {c.ok ? "OK" : "FAIL"}
              </span>{" "}
              <code>{c.chunk_id}</code>{" "}
              <span style={{ opacity: 0.7 }}>
                validated {c.validated_count}, dropped {c.dropped_count}
                {c.fallback_used ? `, fallback=${c.fallback_used}` : ""}
              </span>
            </summary>
            <pre>{JSON.stringify(c, null, 2)}</pre>
          </details>
        </li>
      ))}
    </ul>
  );
}

function LLMCallList({ calls }: { calls: LLMCall[] }) {
  if (calls.length === 0) {
    return <Empty msg="No LLM calls recorded for this step." />;
  }
  return (
    <ul className="step-inspector-list">
      {calls.map((c) => (
        <li key={c.call_id} className="step-inspector-item">
          <details>
            <summary>
              <span className="pill">{c.provider}</span>{" "}
              <code>{c.model}</code>{" "}
              {c.chunk_id && (
                <span style={{ opacity: 0.6 }}>
                  chunk <code>{c.chunk_id}</code>
                </span>
              )}{" "}
              <span style={{ opacity: 0.7 }}>
                {c.latency_ms} ms
                {c.total_tokens !== undefined && c.total_tokens !== null
                  ? ` · ${c.total_tokens} tok`
                  : ""}
                {c.error ? ` · ERROR` : ""}
              </span>
            </summary>
            {c.error && (
              <pre className="error-pre">{c.error}</pre>
            )}
            <details>
              <summary>Messages ({c.messages.length})</summary>
              <pre>{JSON.stringify(c.messages, null, 2)}</pre>
            </details>
            {c.response_structured && (
              <details>
                <summary>Structured response</summary>
                <pre>{JSON.stringify(c.response_structured, null, 2)}</pre>
              </details>
            )}
            <details>
              <summary>Raw response ({c.response_text.length} chars)</summary>
              <pre>{c.response_text}</pre>
            </details>
          </details>
        </li>
      ))}
    </ul>
  );
}

function SectionList({ sections }: { sections: SectionLocation[] }) {
  if (sections.length === 0) {
    return <Empty msg="No section locations recorded for this step." />;
  }
  return (
    <ul className="step-inspector-list">
      {sections.map((s, idx) => (
        <li key={`${s.section_name}-${idx}`} className="step-inspector-item">
          <details>
            <summary>
              <code>{s.section_name}</code>{" "}
              <span style={{ opacity: 0.7 }}>
                chars {s.char_start}–{s.char_end} ({s.char_count} total)
              </span>
              {s.matched_against_real_section ? (
                <span className="pill ok" style={{ marginLeft: 8 }}>
                  Real
                </span>
              ) : (
                <span className="pill fail" style={{ marginLeft: 8 }}>
                  Disclaimer
                </span>
              )}
            </summary>
            <pre>{JSON.stringify(s, null, 2)}</pre>
          </details>
        </li>
      ))}
    </ul>
  );
}

function LifecycleList({ rows }: { rows: RiskLifecycleAnnotation[] }) {
  if (rows.length === 0) {
    return <Empty msg="No lifecycle annotations recorded for this step." />;
  }
  return (
    <ul className="step-inspector-list">
      {rows.map((r) => (
        <li key={r.risk_id} className="step-inspector-item">
          <details>
            <summary>
              <LifecycleBadge
                lifecycle={r.lifecycle}
                confidence={r.confidence}
                reasoning={r.reasoning}
              />{" "}
              <code>{r.risk_id}</code>
              {r.basis.length > 0 && (
                <span style={{ opacity: 0.7 }}>
                  {" "}
                  basis: {r.basis.length} evidence
                </span>
              )}
            </summary>
            <p style={{ margin: "6px 0" }}>{r.reasoning}</p>
            {r.basis.length > 0 && (
              <details>
                <summary>Basis ({r.basis.length})</summary>
                <pre>{JSON.stringify(r.basis, null, 2)}</pre>
              </details>
            )}
            <details>
              <summary>Full record</summary>
              <pre>{JSON.stringify(r, null, 2)}</pre>
            </details>
          </details>
        </li>
      ))}
    </ul>
  );
}

function Empty({ msg }: { msg: string }) {
  return <p className="empty-state">{msg}</p>;
}
