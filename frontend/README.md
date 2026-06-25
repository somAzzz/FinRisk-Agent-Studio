# FinRisk Agent Studio — Frontend

Minimal Vite + React + TypeScript dashboard for the FinRisk Agent Studio
workflow API. Four views, no chat:

1. **Workflow Launcher** — POST `/workflows/finrisk/run`.
2. **Agent Timeline** — polls `GET /workflows/{run_id}` every 1.5s.
3. **Risk Report** — `GET /workflows/{run_id}/report`.
4. **Evidence Graph** — ReactFlow layout of company → risk → evidence → insight.

## Run locally

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173 (proxies /workflows to :8000)
```

In a second terminal, start the backend:

```bash
uv run uvicorn src.api.main:app --reload
```

Open <http://127.0.0.1:5173>, leave defaults (AAPL + demo mode), and
press **Run Risk Workflow**.

## Test

```bash
npm test             # vitest, jsdom
npm run build        # tsc -b && vite build
```

## Layout

```text
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api.ts          # thin fetch wrapper around /workflows/*
    ├── types.ts        # mirrors src/schemas/finrisk.py
    ├── styles.css
    ├── test-setup.ts
    ├── api.test.ts
    └── components/
        ├── WorkflowLauncher.tsx
        ├── AgentTimeline.tsx
        ├── RiskReport.tsx
        ├── EvidenceGraph.tsx
        └── EvaluationPanel.tsx
```

## Tech notes

- ReactFlow is used for the evidence graph; node positions are computed
  deterministically from the report. No force layout in v1.
- The polling loop stops once status reaches a terminal state
  (`completed` / `failed` / `needs_review`).
- The dev server proxies `/workflows` to `http://127.0.0.1:8000`; in
  production, serve the built `dist/` behind a reverse proxy that
  forwards `/workflows` to the FastAPI app.
