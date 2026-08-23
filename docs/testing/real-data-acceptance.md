# Real Data Acceptance Flow

This reusable flow checks that the running project matches the design blueprint with real providers enabled, not demo fixtures or cached-only paths.

## Scope

The flow validates:

- FinRisk workflow: live request with `demo_mode=false` and `cached_mode=false`.
- SEC section extraction: section locations and chunk validations exist.
- LLM extraction: `/workflows/{run_id}/llm_log` has successful calls with prompts, responses, provider, model, latency, and token metadata when available.
- Lifecycle classification: `/workflows/{run_id}/lifecycles` is populated.
- Report and guardrails: report markdown exists, disclaimer language exists, workflow evaluation is not `fail`.
- Supply chain workflow: live request with `demo_mode=false` and `cached_mode=false`.
- Supply chain LLM path: trace contains both `search` and `llm_extract_suppliers` provider calls.
- Sankey payload: nodes, links, evidence, and evidence references are valid.
- Frontend real-mode smoke: optional Playwright check submits real-mode requests and verifies the rendered Risk Intelligence and Product Supply Chain views.

## Prerequisites

Start Qwen3.6 NVFP4 and Neo4j, then wait for the model endpoint. The default
context length is 262144 tokens; set `LLM_MAX_MODEL_LEN` only when you want to
trade context length for more concurrent requests.

```bash
docker compose up -d neo4j
# LLM endpoint must already be running outside this repository.
curl http://127.0.0.1:30000/v1/models
```

Start the API and frontend with the same local API key. Vite injects the key
into proxied development requests without exposing it in the browser bundle.

```bash
set -a; source .env; set +a
FINRISK_API_KEYS=local-real-acceptance \
  uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000

cd frontend
FINRISK_API_KEY=local-real-acceptance \
  npm run dev -- --host 127.0.0.1 --port 5173
```

Start the selected LLM backend and any search/data providers required by `.env`.

For local SGLang:

```bash
export LLM_PROVIDER=sglang
export LLM_BASE_URL=http://localhost:30000/v1
```

For vLLM:

```bash
export LLM_PROVIDER=vllm
export LLM_BASE_URL=http://localhost:30000/v1
```

For cloud providers, set the provider-specific API keys already documented in `.env.example`.

## Run

API + frontend:

```bash
uv run python scripts/real_data_acceptance.py \
  --api-base http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1:5173 \
  --llm-provider vllm \
  --llm-base-url http://localhost:30000/v1
```

When API authentication is enabled, export the client-side key before running:

```bash
export FINRISK_API_KEY=local-real-acceptance
```

API only:

```bash
uv run python scripts/real_data_acceptance.py \
  --skip-frontend \
  --llm-provider vllm \
  --llm-base-url http://localhost:30000/v1
```

The default report is written to:

```text
artifacts/real_data_acceptance/latest.json
```

Use `--output artifacts/real_data_acceptance/<name>.json` to keep multiple runs.

## What It Fails On

The runner fails when:

- API health endpoints are unavailable.
- FinRisk or Supply Chain workflow status is `failed`.
- The request accidentally uses `demo_mode=true` or `cached_mode=true`.
- FinRisk report markdown is empty or lacks disclaimer language.
- FinRisk trace has too few completed steps.
- FinRisk LLM log is empty, has no successful response, or uses the wrong provider.
- Chunk validations, section locations, or lifecycle annotations are empty.
- Workflow evaluation returns `fail`.
- Supply Chain graph has too few nodes, links, or evidence rows.
- Supply Chain trace lacks `search` or `llm_extract_suppliers` provider calls.
- Supply Chain LLM extraction has no successful provider call.
- Confirmed Sankey links reference missing evidence.
- Frontend Playwright real-mode smoke fails.

`needs_review` is allowed. In real data runs, guardrails may correctly downgrade a result because of low source diversity, weak evidence, or provider gaps. That is still a useful, blueprint-aligned outcome as long as it is visible in evaluation, warnings, fallback events, or trace logs.

## Artifacts To Inspect

The JSON report stores:

- `artifacts.finrisk.request`: exact live request.
- `artifacts.finrisk.status`: workflow status, trace summary, risk/evidence counts.
- `artifacts.finrisk.llm_log`: full LLM call rows with prompt/response/error/token fields.
- `artifacts.finrisk.chunks`: per-chunk Pydantic validation rows.
- `artifacts.finrisk.sections`: SEC section match metadata.
- `artifacts.finrisk.lifecycles`: lifecycle classifier output.
- `artifacts.finrisk.evaluation`: workflow-level guardrail result.
- `artifacts.supply_chain.status`: node/link/evidence counts, trace, warnings, fallback events.
- `artifacts.supply_chain.sankey`: full Sankey payload.
- `artifacts.frontend`: Playwright stdout/stderr when frontend checks are enabled.

## Blueprint Coverage Matrix

| Blueprint Area | Acceptance Signal |
| --- | --- |
| Real data path | `demo_mode=false`, `cached_mode=false` in both requests |
| LLM provider selection | request `llm_config` and observed provider in `llm_log` / provider calls |
| Filing parser | non-empty `section_locations` |
| Chunked LLM extraction | non-empty `chunk_validations` and successful `llm_log` rows |
| Pydantic validation | chunk validation rows and no workflow `fail` |
| Lifecycle classifier | non-empty `risk_lifecycles` |
| Report generator | non-empty report markdown with disclaimer |
| Quality layer | evaluation endpoint and trace artifacts |
| Supply chain search | `search:success` provider calls in supply-chain trace |
| Supply chain LLM extraction | `llm_extract_suppliers:success` provider calls |
| Evidence-backed graph | Sankey links reference existing evidence IDs |
| Frontend real mode | Playwright intercepts real-mode payloads and rendered outputs |

## CI Usage

This flow is intended for an integration lane, not the fast unit-test lane:

```bash
RUN_REAL_DATA_ACCEPTANCE=1 uv run python scripts/real_data_acceptance.py --skip-frontend
```

Keep provider keys and local model endpoints outside the repository. Save the generated JSON report as a CI artifact so LLM prompts, responses, and provider failures can be audited after the run.
