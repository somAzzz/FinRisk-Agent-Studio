# Spec 05 - Frontend Dashboard

## 目标

实现 FinRisk Agent Studio 的最小可展示前端。前端不是聊天窗口，而是一个 Agent Workflow Dashboard。

## 范围

第一版只需要 4 个视图：

1. Workflow Launcher
2. Agent Timeline
3. Risk Report
4. Evidence Graph

## 技术选择

如果项目尚无前端，建议：

```text
Vite + React + TypeScript
ReactFlow
```

候选依赖：

```text
@vitejs/plugin-react
react
react-dom
reactflow
lucide-react
```

如果项目已有前端框架，应复用现有框架。

## 推荐目录

```text
frontend/
├── package.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api.ts
│   ├── types.ts
│   ├── components/
│   │   ├── WorkflowLauncher.tsx
│   │   ├── AgentTimeline.tsx
│   │   ├── RiskReport.tsx
│   │   ├── EvidenceGraph.tsx
│   │   └── EvaluationPanel.tsx
│   └── styles.css
```

## 页面 1：Workflow Launcher

字段：

- ticker
- company name optional
- analysis goal
- time horizon
- sources
- max browser steps
- demo mode
- cached mode

默认值：

```text
ticker: AAPL
analysis goal: Identify macro, policy and supply-chain risks that changed recently.
time horizon: 6-12 months
sources: filing, web, graph
demo mode: true
cached mode: true
```

行为：

- 点击 Run Workflow 调用 `POST /workflows/finrisk/run`。
- 成功后进入 timeline 状态。
- 请求失败显示错误。

## 页面 2：Agent Timeline

展示 8 个 step：

```text
Company Resolver
Filing Risk Extractor
Market Explorer
Evidence Normalizer
Risk Scorer
Graph Reasoner
Report Generator
Evaluation
```

每一步展示：

- status icon
- duration
- input summary
- output summary
- error
- retry count

数据来源：

```text
GET /workflows/{run_id}
```

刷新策略：

- 第一版轮询，每 1-2 秒一次。
- status 为 completed / failed / needs_review 后停止轮询。

## 页面 3：Risk Report

展示：

- Executive Summary
- Top Risks
- Risk Scores
- Recent Changes
- Evidence Table
- Second-Order Effects
- Evidence vs Inference
- Confidence & Limitations
- Recommended Next Research Questions

要求：

- evidence quote 要可展开。
- source URL 可点击。
- severity 使用 1-5 的视觉标记。
- confidence 使用 0-1 或百分比。
- 不要把整个 markdown 原样塞进一个不可读文本框。

数据来源：

```text
GET /workflows/{run_id}/report
```

## 页面 4：Evidence Graph

使用 ReactFlow 展示：

```text
Company → Risk → Evidence → Supplier / Policy / Market Factor
```

节点类型：

- company
- risk
- evidence
- supplier/customer
- policy/geopolitical factor
- opportunity

边类型：

- HAS_RISK
- SUPPORTED_BY
- EXPOSED_TO
- AFFECTS
- SUGGESTS_OPPORTUNITY

第一版 graph 数据可由 report API 中的 `top_risks`、`evidence_table`、`graph_insights` 生成。

## UI 设计约束

- 第一屏就是可用 app，不做 landing page。
- 不做聊天界面。
- 页面布局偏工作台风格，信息密度适中。
- 卡片只用于独立 repeated items，不要卡片套卡片。
- 工具按钮优先使用 icon。
- 所有移动端和桌面端文本不能溢出。
- 不使用大面积单一紫色/蓝紫渐变。

## Error states

必须处理：

- API 不可用。
- workflow failed。
- workflow needs_review。
- report not ready。
- graph insight 为空。
- evidence 为空。

## Frontend tests

第一版至少需要：

- API client mock test。
- launcher submit test。
- timeline render test。
- report render with fixture test。
- graph render with fixture test。

若测试栈尚未建立，可以先用 TypeScript build 和手动 fixture smoke test 作为验收。

## 验收流程

启动后端：

```bash
uvicorn src.api.main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

手动验收：

```text
打开前端
输入 AAPL
开启 demo mode
Run Workflow
看到 timeline 逐步完成
看到 report
看到 evidence graph
看到 evaluation status
```

## 完成定义

- 前端可以完成一次 demo workflow。
- timeline 能显示 step 状态。
- report 可读。
- graph 非空。
- failed / needs_review 状态有明确展示。

