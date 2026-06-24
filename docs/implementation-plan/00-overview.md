# Step 00 - 实施总览与任务拆分

## 目标

本目录把 `docs/architecture-roadmap-cn.md` 拆成可执行的分步工程计划。每个步骤都是一份独立任务说明书，可以交给不同编程助手实现。

最终系统目标：

> 输入一个 ticker，系统自动读取历史年报、最新 SEC filing、电话会议和网页信息，抽取风险、机会、供应链关系、管理层情绪、政策和地缘政治暴露，写入 Neo4j，并生成带证据链的研究假设。

## 执行顺序

建议严格按以下顺序推进：

1. `01-shared-schemas-and-config.md`
2. `02-edgar-hf-streaming-loader.md`
3. `03-sec-api-and-filing-fetcher.md`
4. `04-transcript-ingestion.md`
5. `05-search-router-and-web-cache.md`
6. `06-llm-agent-runtime.md`
7. `07-extraction-pipelines.md`
8. `08-neo4j-supply-chain-graph.md`
9. `09-risk-sentiment-policy-geo.md`
10. `10-opportunity-discovery-and-reporting.md`
11. `11-evaluation-and-mvp-demo.md`
12. `12-stabilization-and-next-steps.md`
13. `13-production-execution-roadmap.md`
14. `14-current-progress-and-next-plan.md`
15. `15-finrisk-agent-studio-workflow-roadmap.md`

## 当前代码基础

已有模块：

- `src/data/loader.py`：本地 EDGAR JSONL loader
- `src/llm/client.py`：风险抽取 LLM client
- `src/llm/sglang_client.py`：SGLang/OpenAI-compatible structured output client
- `src/tools/web_search.py`：DuckDuckGo 搜索工具
- `src/tools/web_fetch.py`：静态网页 fetch + trafilatura 抽取
- `src/tools/router.py`：初版工具路由
- `src/browser/*`：agent-browser 网页探索
- `scripts/compare_tools/*`：工具质量对比脚本

## 全局工程约束

所有步骤都应遵循：

- 使用 Python 3.12。
- 使用 Pydantic 定义结构化输入和输出。
- 所有 LLM 结论必须携带 evidence。
- 所有外部 API client 都要支持 timeout、重试、速率限制和明确错误类型。
- 不要把 API key 写入代码；统一从环境变量读取。
- 测试优先使用 mock，不依赖真实外网，真实 API 集成测试应可选。
- 保留现有测试，避免破坏 `src/browser`、`src/tools` 和 `src/llm` 的已有行为。

## 推荐目录结构

最终建议形成：

```text
src/
├── agents/
├── data/
│   └── providers/
├── graph/
├── pipelines/
├── schemas/
├── tools/
│   └── providers/
├── evaluation/
└── api/
```

## 跨步骤共享概念

后续文档会反复使用以下概念：

- `Evidence`：证据片段，指向 filing、transcript、web article 或 API response。
- `Entity`：公司、产品、地区、政策、人物、商品等实体。
- `Relation`：实体之间的供应、客户、竞争、暴露、受益、风险等关系。
- `Claim`：LLM 或 pipeline 产生的研究判断。
- `Hypothesis`：由多个 claim 和 evidence 组成的投资研究假设。
- `AgentState`：Agent 执行过程中的任务目标、上下文、工具历史和中间结论。

## 完成定义

当所有步骤完成后，应至少支持一个端到端命令：

```bash
python -m src.pipelines.analyze_company --ticker AAPL --year 2024
```

输出应包含：

- 公司基础信息
- 最近 filing 和 transcript 摘要
- 上下游供应链关系
- 管理层情绪
- 政策和地缘政治风险
- 潜在机会假设
- 每条结论对应 evidence
- 可选写入 Neo4j

## 当前实现后的稳定化步骤

在完成初版骨架实现后，先执行：

```text
docs/implementation-plan/12-stabilization-and-next-steps.md
```

该文档记录了当前代码审核结果、测试失败原因、修正方案和下一步功能优先级。后续编程助手应优先完成 Step 12 中的 P0/P1 任务，再继续扩展新功能。

## 正式项目执行路线图

完成稳定化后，后续工作应以正式项目目标推进，而不是继续围绕离线 demo 扩展：

```text
docs/implementation-plan/13-production-execution-roadmap.md
```

该文档按真实 SEC filing、电话会议、网页搜索、LLM 结构化抽取、Neo4j 图推理、风险/机会研究和 API 服务层拆分后续执行阶段。

## 最近提交复盘与下一步安排

在 Step 13 之后，应继续参考：

```text
docs/implementation-plan/14-current-progress-and-next-plan.md
```

该文档基于最近本地 Git 提交重新评估当前实现进度，并把下一步拆成质量收口、真实 SEC 数据闭环、电话会议、网页搜索、LLM Agent、Neo4j 图推理、政策/地缘风险和评估回测等执行阶段。

## Agent Workflow 产品化路线

在正式生产路线之外，还应参考：

```text
docs/implementation-plan/15-finrisk-agent-studio-workflow-roadmap.md
```

该文档把当前工具库和 pipeline 重新组织为 `FinRisk Agent Studio`：一个可运行、可解释、可评估、可部署的 Agent Workflow Demo。它重点规划 workflow skeleton、Pydantic structured outputs、guardrails、evaluation、FastAPI、前端 timeline/report/graph，以及 local-LLM/API 双运行模式。
