# Local LLM E2E API and Frontend Report - 2026-06-27

## Scope

Objective: run real end-to-end cases against the locally running Docker stack and
local SGLang LLM, exercise backend APIs and frontend flows, monitor logs, fix
blocking defects, and record remaining issues.

## Environment

- Docker services:
  - `fintext_llm-sglang-1`: `lmsysorg/sglang:v0.5.14-cu130-runtime`, exposed on
    `http://127.0.0.1:30000/v1`, model `Qwen/Qwen3.5-35B-A3B`.
  - `fintext_llm-neo4j-1`: `neo4j:5.26.0`, ports `7474` and `7687`.
- Backend:
  - `uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000`
  - `AUTH_DISABLED=1`, `RATE_LIMIT_DISABLED=1`
  - `LLM_PROVIDER=sglang`
  - `SGLANG_BASE_URL=http://127.0.0.1:30000/v1`
  - `SGLANG_MODEL=Qwen/Qwen3.5-35B-A3B`
  - `RUN_STORE_BACKEND=sqlite`
  - `RUN_STORE_DB=.cache/fintext_llm/e2e-runs.sqlite3`
- Frontend:
  - `npm run dev -- --host 127.0.0.1 --port 5173`
  - Earlier startup required `CHOKIDAR_USEPOLLING=true` on this host because the
    default Vite watcher hit the OS file-watcher limit (`ENOSPC`).

## Current Real-Case Results

### FinRisk API, real AAPL run

- Request:
  - `POST /workflows/finrisk/run`
  - ticker `AAPL`, company `Apple Inc.`
  - `demo_mode=false`, `cached_mode=false`
  - sources `filing`, `web`, `graph`
  - LLM config `sglang`, base URL `http://127.0.0.1:30000/v1`, model
    `Qwen/Qwen3.5-35B-A3B`
- Run id: `run-9e2a88966825`
- Result:
  - final status `needs_review`
  - status polling timeouts: `0`
  - risks: `41`
  - evidence rows: `41`
  - report endpoint `GET /workflows/run-9e2a88966825/report`: `200 OK`
  - report markdown length: `7031`
  - evaluation: schema valid, evidence present for each risk, no unsupported
    claims, no financial-advice risk, hallucination risk `0.0`, source diversity
    `0.0244`, final status `needs_review`

This proves the backend no longer starves the FastAPI event loop during a real
local-LLM run; status polling remained responsive throughout the workflow.

### FinRisk frontend

- Page: `http://127.0.0.1:5173/`
- Flow: disabled demo mode, ran AAPL FinRisk workflow from the UI.
- Result:
  - rendered report and timeline
  - no page errors or console errors
  - screenshot: `demo_output/frontend-finrisk-e2e.png`

### Supply-chain API, real OpenAI / ChatGPT run

- Request:
  - `POST /supply-chain/explore`
  - company `OpenAI`, product `ChatGPT`
  - `demo_mode=false`, `cached_mode=false`
  - LLM config points at local SGLang
- Run id: `sc-run-44ec2a062452`
- Result:
  - final status `needs_review`
  - nodes: `11`
  - links: `11`
  - evidence rows: `5`
  - metrics: `requirement_count=6`, `query_count=6`, `raw_result_count=16`,
    `candidate_count=5`, `evidence_row_count=5`, `supplier_edge_count=5`
  - warnings: none
  - fallback events: none

The supply-chain API now produces evidence-backed output for the real
OpenAI / ChatGPT case.

### Supply-chain frontend

- Page: `http://127.0.0.1:5173/`
- Flow: ran the supply-chain explorer UI.
- Result:
  - Sankey view rendered
  - no page errors or console errors
  - screenshot: `demo_output/frontend-supply-chain-e2e.png`

### Agent Runs API

- Request:
  - `POST /agent-runs`
  - workflow `generic_research`
  - provider `sglang`
  - tool loop mode `native`
  - tool scope `company_research`
  - no explicit `base_url` or `model`, verifying provider defaults and native
    `tool_choice="required"` behavior
- Run id: `agent-32446fffe779`
- Result:
  - final status `completed`
  - tool events: `1`
  - evidence candidates: `1`
  - human review items: `0`
  - fallback events: none
  - first tool: `web_search`

This proves the API is asynchronous, default SGLang routing no longer points at
the backend's `/v1`, and native SGLang/Qwen tool calls now execute through the
agent loop.

### Agent Runs frontend

- Page: `http://127.0.0.1:5173/`
- Flow:
  - opened the Agent Runs tab
  - selected workflow `Generic Research`
  - selected provider `SGLang`
  - selected tool scope `company_research`
  - selected tool loop `Native`
  - submitted a real local-LLM run
- Run id observed in UI: `agent-eb2cb9c1a2d6`
- Result:
  - frontend reached terminal status `completed`
  - tool events: `2`
  - accepted evidence: `1`
  - review items: `0`
  - Vite proxy returned `202` for `POST /agent-runs`
  - timeline and trace polling returned `200`
  - no error banner
  - no page errors
  - screenshot: `demo_output/frontend-agent-runs-e2e.png`

## Defects Found and Fixed

1. `FilingRiskExtractorStep` passed `chunk_overlap=` to
   `EdgarLLMClient.extract_risks_chunked`, but the client expects `overlap=`.
   This made real filing extraction fall back instead of using the live LLM.
   Fixed in `src/workflows/steps/filing_risk_extractor.py`.

2. `extract_risks_chunked` referenced a nonexistent `chunk.chunk_id`.
   Fixed by deriving a stable chunk id from source, section, and offsets in
   `src/llm/client.py`.

3. Qwen/SGLang returned reasoning preambles and schema-incomplete JSON for risk
   extraction. Fixed by disabling thinking for SGLang chat calls, adding
   `risk_type` to the prompt, and normalizing risk types in `src/llm/client.py`.

4. Chunk extraction emitted duplicate `llm_log` rows. Fixed by suppressing
   per-attempt call emission and emitting one final call per chunk.

5. Real FinRisk workflow execution blocked the FastAPI event loop. Fixed by
   running the blocking workflow in a worker thread from `src/api/workflows.py`.

6. Vite did not proxy `/agent-runs`, so the Agent Runs UI posted to Vite and
   got `404`. Fixed in `frontend/vite.config.ts`.

7. `POST /agent-runs` ran synchronously and could leave the UI waiting. Fixed by
   returning `202 Accepted`, retaining background tasks, and running the global
   runtime in a worker thread in `src/api/agent_runs.py`.

8. The Agent Runs panel did not poll after a queued response. Fixed in
   `frontend/src/components/LLMAgentRunPanel.tsx`.

9. Agent Runs with provider `sglang` but no request `base_url/model` defaulted
   incorrectly and could call the backend itself at `/v1`. Fixed provider
   defaults in `src/pipelines/llm_tool_research.py`.

10. JSON fallback tool loop prepended a second `system` message. SGLang rejects
    that shape with `System message must be at the beginning`. Fixed by merging
    the fallback tool instructions with the original system prompt in
    `src/llm/tool_loop.py`.

11. The global agent runtime marked tool failures, and no-tool subgoals, as
    completed. Fixed in `src/agents/global_runtime.py` so failed tool execution
    becomes `failed`, and no-tool evidence becomes `needs_review` with a review
    item and trace event.

12. Supply-chain Neo4j writes failed when node, edge, or evidence metadata
    contained nested maps. Neo4j properties must be primitives or arrays, so the
    writer now serializes nested values at the write boundary in
    `src/graph/supply_chain_writer.py`. Re-running the OpenAI / ChatGPT
    supply-chain case with backend `NEO4J_*` credentials removed the
    `Neo4j write failed` fallback.

13. SGLang/Qwen did not return structured `tool_calls` because the server was
    running without a Qwen tool parser. `docker-compose.yml` now starts
    `Qwen/Qwen3.5-35B-A3B` with `--tool-call-parser qwen`,
    `--reasoning-parser qwen3`, `--grammar-backend xgrammar`, and
    `--trust-remote-code`. A direct `/v1/chat/completions` smoke test with
    `tool_choice="required"` now returns one structured `web_search` tool call.

14. Evidence-producing Agent Runs now force native tool use when the subgoal
    declares `required_evidence_types`. The runtime passes
    `tool_choice="required"` for native OpenAI-compatible tool loops, while
    retaining the no-tool guard for framework/model failures.

15. Supply-chain discovery returned zero evidence because the DuckDuckGo provider
    depended on optional search packages that were not declared. The project now
    declares `ddgs>=9.0.0`, and real OpenAI / ChatGPT supply-chain discovery
    produced `5` evidence rows.

16. Supply-chain discovery now records metrics so failures are diagnosable:
    `requirement_count`, `query_count`, `raw_result_count`, `candidate_count`,
    `evidence_row_count`, and `supplier_edge_count`. The status API exposes
    these metrics.

17. Local `.env` now quotes `SEC_USER_AGENT`, and `source .env` prints the
    expected full value without shell errors.

18. `npm run dev` now defaults to `CHOKIDAR_USEPOLLING=true vite --host
    127.0.0.1 --port 5173`; `dev:normal` remains available for environments
    that do not need polling.

## Verification Commands

- `uv run ruff check src/api/agent_runs.py src/agents/global_runtime.py src/api/workflows.py src/llm/client.py src/llm/tool_loop.py src/pipelines/llm_tool_research.py src/workflows/steps/filing_risk_extractor.py src/graph/supply_chain_writer.py tests/api/test_agent_runs_api.py tests/agents/test_global_agent_runtime.py tests/llm/test_client.py tests/llm/test_tool_loop.py tests/graph/test_supply_chain_writer.py tests/supply_chain/test_graph_builder.py`
- `uv run pytest tests/agents/test_global_agent_runtime.py tests/api/test_agent_runs_api.py tests/llm/test_client.py tests/llm/test_tool_loop.py tests/api/test_workflow_api.py tests/api/test_workflow_task_retention.py tests/workflows/test_real_mode_fallbacks.py tests/graph/test_supply_chain_writer.py tests/supply_chain/test_graph_builder.py -q`
  - Result: `46 passed`
- `uv run pytest tests/api/test_agent_runs_api.py tests/api/test_supply_chain_api.py tests/supply_chain/test_supplier_discovery.py tests/graph/test_supply_chain_writer.py tests/llm/test_tool_loop.py tests/llm/test_client.py tests/agents/test_global_agent_runtime.py -q`
  - Result: `39 passed`
- `npm run build`
  - Result: success
- `npm run test`
  - Result: `38 passed`

## Follow-up Closure - 2026-06-27

All four previously listed follow-ups were retested and closed.

1. Agent Runs tool calling:
   - direct SGLang smoke test with `tool_choice="required"` returned one
     structured `web_search` tool call;
   - real Agent Runs API run `agent-32446fffe779` completed with one tool event,
     one evidence candidate, and no fallback events.

2. Supply-chain evidence:
   - real OpenAI / ChatGPT run `sc-run-44ec2a062452` returned status
     `needs_review`, `11` nodes, `11` links, and `5` evidence rows;
   - metrics: `requirement_count=6`, `query_count=6`, `raw_result_count=16`,
     `candidate_count=5`, `evidence_row_count=5`, `supplier_edge_count=5`;
   - warnings and fallback events were empty.

3. `.env`:
   - `SEC_USER_AGENT="FinText-LLM contact@example.com"`;
   - `source .env` succeeds and prints `<FinText-LLM contact@example.com>`.

4. Frontend dev server:
   - `npm run dev` now enables polling by default;
   - `npm run build` and `npm run test` both pass.
