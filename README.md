# FinText-LLM

FinText-LLM is evolving into **FinRisk Agent Studio**: an AI-native financial risk intelligence workflow that combines SEC filings, web evidence, local or API-based LLMs, structured outputs, graph reasoning, and runtime quality guardrails.

The project goal is not a generic “chat with filings” demo. It is a workflow system for financial research:

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
→ Graph Reasoning
→ Structured Report Generation
→ Quality Layer / Human Review Gate
```

## Current Direction

The latest roadmap reframes the project around two core ideas:

1. **Quality Layer across every step**
   Evaluation and guardrails should not only run after the report is generated. Every workflow step should have pre-step and post-step validation, including schema checks, evidence coverage, claim grounding, source quality, financial safety, graph path validation, and fallback tracking.

2. **Graph Reasoning as a subsystem**
   Graph reasoning should not mean giving an entire graph to an LLM. The intended design is:

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ LLM / Template Path Interpreter
→ Graph Insight Validator
→ Evidence Graph Visualization
```

LLMs explain verified paths and generate research hypotheses. They do not invent graph paths, create unsupported facts, or issue buy/sell recommendations.

## What This Project Demonstrates

- Pydantic-first agent workflow design
- Local LLM and OpenAI-compatible API provider support
- SEC EDGAR filing analysis
- Targeted market evidence collection
- Evidence-backed risk extraction
- Deterministic risk scoring
- Claim-to-evidence grounding
- Graph path retrieval and ranking
- Runtime guardrails and human review gates
- Cached demo mode for reliable presentations
- FastAPI and dashboard-oriented productization

## Planned Demo: FinRisk Agent Studio

Example user request:

```text
Company: Apple
Ticker: AAPL
Analysis Goal: Identify macro, policy and supply-chain risks that changed recently.
Time Horizon: next 6-12 months
```

Expected output:

- Top risks with severity and score breakdown
- Filing evidence and recent market evidence
- Claim-evidence matrix
- Source quality warnings
- Supply-chain or policy graph paths
- Second-order risk insights
- Structured risk intelligence report
- Guardrail findings and human review status
- Evidence graph visualization

## Existing Foundation

The repository already contains foundational modules for:

- EDGAR data loading
- SEC filing access and section parsing
- Hugging Face EDGAR corpus loading
- SGLang / OpenAI-compatible structured LLM client
- Browser exploration
- Search routing and caching
- Risk, sentiment, opportunity, and report agents
- Neo4j graph writer/query components
- Offline demo fixtures and tests
- Roadmap and implementation specs

## Roadmap Documents

Start here:

```text
docs/implementation-plan/00-overview.md
```

Most important current plans:

```text
docs/implementation-plan/15-finrisk-agent-studio-workflow-roadmap.md
docs/implementation-plan/16-quality-layer-and-graph-reasoning-roadmap.md
```

Step 15 combined spec:

```text
docs/specs/v15-finrisk-agent-studio/15-finrisk-agent-studio-combined-spec.md
```

Step 16 detailed specs:

```text
docs/specs/v16-quality-graph/00-index.md
docs/specs/v16-quality-graph/01-quality-layer-runtime.md
docs/specs/v16-quality-graph/02-claim-grounding-and-source-quality.md
docs/specs/v16-quality-graph/03-graph-reasoning-subsystem.md
docs/specs/v16-quality-graph/04-structured-report-and-risk-scoring.md
docs/specs/v16-quality-graph/05-api-and-frontend-quality-graph.md
docs/specs/v16-quality-graph/06-v16-demo-acceptance.md
```

## Target Architecture

```text
src/
├── agents/
├── api/
├── browser/
├── data/
├── evaluation/
│   ├── engine.py
│   ├── models.py
│   ├── validators/
│   └── metrics/
├── graph/
├── graph_reasoning/
├── llm/
├── reports/
├── schemas/
├── tools/
└── workflows/
    ├── finrisk_workflow.py
    ├── state.py
    └── steps/

frontend/
eval/
docs/
tests/
```

## Workflow Quality Layer

The V16 plan introduces a runtime quality layer:

```text
Layer 1: Schema & Contract Guardrails
Layer 2: Evidence & Grounding Guardrails
Layer 3: Domain & Financial Safety Guardrails
Layer 4: Workflow Quality & Regression Evaluation
```

Examples of checks:

- Pydantic schema validity
- required fields present
- risk/evidence/claim ID references valid
- each top risk has evidence
- each claim has supporting evidence IDs
- source quality and source diversity
- no direct buy/sell advice
- graph path exists in graph
- graph edge has evidence or is marked as hypothesis
- fallback events are recorded

## Graph Reasoning

The intended graph flow:

```text
Company + Risks + Evidence
→ Graph Query Context
→ Candidate Graph Paths
→ Path Score Breakdown
→ Evidence Binding
→ Path Interpretation
→ Graph Insight Validation
→ Evidence Graph Payload
```

Example graph path:

```text
Apple
→ depends_on
TSMC
→ located_in
Taiwan
→ exposed_to
Geopolitical Risk
```

Insights are allowed to become **research themes** or **hypotheses**, not financial advice.

## Quick Start

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest -q
```

Run the existing offline company analysis demo:

```bash
uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

The planned FinRisk workflow CLI target is:

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## Optional Local LLM Setup

The project can use SGLang for local LLM inference:

```bash
docker compose up -d
```

The planned provider configuration:

```text
LLM_PROVIDER=sglang
LLM_PROVIDER=openai
LLM_PROVIDER=gemini
LLM_PROVIDER=claude
LLM_BASE_URL=http://localhost:30000/v1
LLM_MODEL=Qwen/Qwen3.5-35B-A3B
```

Demo mode should not require GPU, API keys, Neo4j, browser automation, or live network access.

## Browser Exploration

Browser exploration is supported as an optional evidence acquisition path. It should not be the only demo path.

Preferred evidence acquisition order:

```text
1. Cached evidence
2. SearchRouter / structured search
3. Browser exploration
```

Optional setup:

```bash
cargo install agent-browser
agent-browser install
```

## Planned API

Minimum API:

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
```

V16 API extensions:

```text
GET /workflows/{run_id}/trace
GET /workflows/{run_id}/graph
GET /workflows/{run_id}/evaluation
GET /workflows/{run_id}/artifacts
```

Planned server command:

```bash
uvicorn src.api.main:app --reload
```

## Planned Dashboard

The dashboard should be a workflow product UI, not a chat interface.

Tabs:

```text
Launcher
Timeline
Risk Report
Evidence Graph
Evaluation
```

The Evaluation tab should expose:

- Evaluation overview
- Step quality timeline
- Claim-evidence matrix
- Risk score breakdown
- Guardrail findings drawer
- Source quality warnings
- Graph path validation status

## Development Priorities

Recommended next order:

1. Stabilize current code and push committed docs.
2. Implement workflow schemas and state.
3. Implement cached MVP workflow.
4. Add runtime Quality Layer.
5. Add claim grounding and source quality.
6. Add graph reasoning subsystem with fixture graph.
7. Generate structured report model and markdown renderer.
8. Expose API endpoints.
9. Build dashboard tabs.
10. Replace fixtures with real SEC, web, transcript, and Neo4j integrations.

## Non-Goals

The first demo should not try to solve everything:

- No direct investment advice
- No buy/sell recommendations
- No requirement for live browser success
- No requirement for GPU
- No requirement for API keys
- No requirement for live Neo4j
- No generic chatbot UI

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
