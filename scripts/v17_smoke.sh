#!/usr/bin/env bash
# v17 regression smoke script.
#
# Runs the full v17 acceptance suite in one go. The script never
# touches the network; demo mode keeps everything offline. Use
# this from a local workstation or a CI runner.
#
# Usage:
#   bash scripts/v17_smoke.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> [1/5] Backend core tests (workflows, evaluation, graph_reasoning, api)"
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api -q

echo "==> [2/5] v16 contract + state round-trip + frontend contract"
uv run pytest tests/schemas tests/reports tests/frontend_contract -q

echo "==> [3/5] Ruff core-dirs gate"
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api

echo "==> [4/5] Frontend tests + build"
(
  cd frontend
  npm test -- --run
  npm run build
)

echo "==> [5/5] CLI demo smoke"
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode

echo
echo "v17 smoke: all checks passed"
