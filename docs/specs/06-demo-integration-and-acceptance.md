# Spec 06 - Demo Integration 与最终验收

## 目标

定义 FinRisk Agent Studio 第一版完整 demo 的集成方案和验收标准，确保它可以在 5 分钟内稳定展示。

## Demo 核心场景

输入：

```text
Ticker: AAPL
Analysis Goal: Identify macro, policy and supply-chain risks that changed recently.
Time Horizon: 6-12 months
Mode: demo/cached
```

输出：

- workflow timeline
- top risks
- filing evidence
- recent market evidence
- risk scores
- graph insights
- risk intelligence report
- evaluation result

## Demo mode 数据要求

新增或复用 fixture：

```text
tests/fixtures/finrisk/aapl_demo_workflow.json
tests/fixtures/finrisk/aapl_filing_risks.json
tests/fixtures/finrisk/aapl_market_evidence.json
tests/fixtures/finrisk/aapl_graph_insights.json
```

fixture 必须包含：

- 至少 3 条 filing risks。
- 至少 5 条 normalized evidence。
- 至少 2 种 source type。
- 至少 1 条 supply-chain 或 geopolitical graph insight。
- 至少 1 条 policy 或 regulatory risk。

## Cached fallback 要求

以下服务不可用时，demo 仍能运行：

- LLM
- browser
- web search provider
- Neo4j
- SEC network request

fallback 策略：

```text
LLM unavailable → cached structured extraction
browser unavailable → SearchRouter/cached evidence
Search unavailable → fixture market evidence
Neo4j unavailable → fixture graph insights
SEC unavailable → cached filing text / filing risks
```

trace 中必须记录 fallback 原因。

## 后端集成验收

运行：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

必须满足：

- exit code 为 0。
- 输出 run_id。
- state.status 为 completed 或 needs_review。
- trace 至少包含 8 个 step。
- report markdown 包含 required sections。
- evaluation 存在。
- 没有直接买卖建议。

## API 集成验收

启动：

```bash
uvicorn src.api.main:app --reload
```

执行：

```bash
curl -X POST http://127.0.0.1:8000/workflows/finrisk/run \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "analysis_goal": "Identify macro, policy and supply-chain risks that changed recently.",
    "sources": ["filing", "web", "graph"],
    "demo_mode": true,
    "cached_mode": true
  }'
```

必须满足：

- 返回 run_id。
- 可以通过 `GET /workflows/{run_id}` 查询状态。
- 可以通过 `GET /workflows/{run_id}/report` 获取 report。

## 前端集成验收

步骤：

1. 启动后端。
2. 启动前端。
3. 打开 dashboard。
4. 使用默认 AAPL demo。
5. 点击 Run Workflow。

必须看到：

- launcher 表单。
- timeline 逐步更新。
- report 页面非空。
- evidence graph 非空。
- evaluation status 展示。

## 测试矩阵

### Offline demo

```bash
uv run pytest tests/workflows -q
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
```

必须通过。

### API smoke

```bash
uv run pytest tests/api -q
```

必须通过。

### Evaluation

```bash
uv run python eval/run_eval.py
```

必须通过或仅返回 needs_review，不允许 fail。

### Existing project tests

```bash
uv run pytest -q
```

必须通过。

## 非目标

第一版 demo 不要求：

- 完整真实 SEC/transcript/web/Neo4j 生产闭环。
- 复杂权限系统。
- 长期 run 持久化。
- 多用户协同。
- 高级图布局。
- 投资建议或交易信号。

## Release checklist

发布 demo 前检查：

- `uv run pytest -q` 通过。
- workflow demo CLI 通过。
- API smoke 通过。
- front-end build 通过。
- README 有运行说明。
- demo script 有 5 分钟讲解路线。
- cached fixture 不包含 API key 或敏感信息。
- 报告明确写明不是投资建议。

## 完成定义

当一个新开发者按 README 可以在本地完成以下流程时，本阶段完成：

```text
install dependencies
start API
start frontend
run AAPL demo
inspect timeline
read report
inspect evidence graph
see evaluation result
```

且整个流程不依赖 GPU、不依赖真实 API key、不依赖外网。

