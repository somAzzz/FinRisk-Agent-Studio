# Step 13 - 正式项目下一步执行路线图

## 目标

本文件不是 MVP 修补清单，而是面向 FinText-LLM 正式项目目标的下一阶段执行方案。

项目最终形态：

> 一个本地 LLM 驱动的金融研究 Agent 系统，能够持续读取 SEC filing、Hugging Face EDGAR 历史语料、电话会议、网页新闻和结构化财务数据，抽取公司业务、供应链、风险、政策暴露、地缘政治暴露和潜在机会，写入 Neo4j 图数据库，并生成带证据链的研究假设。

当前仓库已经具备大量基础模块：

- shared schemas
- SEC client 和 ticker resolver
- Hugging Face EDGAR loader
- transcript provider 抽象
- SearchRouter 和 cache
- Agent runtime 骨架
- extraction/risk/sentiment/opportunity/report agents
- Neo4j graph writer/query
- offline demo 和测试体系

下一阶段的重点不再是“能跑一个 DEMO”，而是让系统具备真实数据闭环、图谱推理能力和可验证研究输出。

## 执行原则

后续所有实现必须遵循：

- 真实数据优先：优先打通 AAPL/NVDA/MSFT 等真实公司，而不是继续扩展 demo fixture。
- 证据链优先：没有 evidence 的 claim 不能进入最终报告正文。
- 图数据库优先：供应链和机会发现必须逐步从 list-based reasoning 转向 graph-based reasoning。
- Agent 可控优先：LLM 只做结构化抽取和推理，关键写入、评分、去重和审核由代码控制。
- 可回测优先：所有研究假设应能保留时间戳、数据源和版本，后续可做历史验证。
- 质量门禁渐进：先保证测试全绿，再逐步扩大 ruff 和 integration test 覆盖范围。

## 当前状态基线

截至本文件制定时，当前状态应以以下命令为基线：

```bash
uv run pytest -q
```

预期：

```text
352 passed, 1 skipped
```

当前仍需注意：

- 工作区可能存在未提交实现，请先完成 code review 后提交。
- 核心目录 ruff 仍有剩余问题。
- Neo4j 的 `entity_id` / `claim_id` / `evidence_id` 需要保持查询和写入一致。
- offline report 已能生成供应链信息，但真实 SEC/transcript/web 数据闭环仍需验证。

## Phase 1：稳定化收口和图数据库一致性

### 目标

把当前已实现的稳定化改动收口为可提交、可验证的工程基线。

### 任务 1.1：提交前代码审核

涉及：

```text
pyproject.toml
src/browser/wrapper.py
src/agents/report_agent.py
src/pipelines/analyze_company.py
src/pipelines/rule_supply_chain.py
src/data/ticker_resolver.py
src/graph/writer.py
src/graph/queries.py
src/graph/schema.cypher
tests/
```

检查点：

- 不提交 cache、venv、pyc、DS_Store。
- `uv run pytest -q` 通过。
- offline report 中 `Supply Chain Map` 非空。
- 文档 Step 12 与当前代码状态一致。

### 任务 1.2：统一 Neo4j 主键和 schema 字段

设计原则：

- 所有 Neo4j 节点统一使用 `entity_id` 作为 MERGE key。
- `Evidence` 节点必须同时保留：
  - `entity_id`
  - `evidence_id`
- `Claim` 节点必须同时保留：
  - `entity_id`
  - `claim_id`
- 查询可以用 `entity_id` 作为主键，但读回 Pydantic schema 时不能丢失原始字段。

涉及文件：

```text
src/graph/writer.py
src/graph/queries.py
src/graph/schema.cypher
tests/graph/test_writer.py
tests/graph/test_queries.py
```

验收标准：

```bash
uv run pytest tests/graph -q
```

并且以下函数语义一致：

- `write_claim()`
- `write_evidence()`
- `get_claim_evidence()`

### 任务 1.3：更新 Step 12 文档状态

涉及：

```text
docs/implementation-plan/12-stabilization-and-next-steps.md
```

更新内容：

- P0 测试入口：标记完成。
- BrowserWrapper 优雅降级：标记完成。
- Slack token 测试：标记完成。
- report evidence 去重：标记完成或记录剩余语义重复。
- supply chain rule extraction：标记完成，但说明只是 fallback。
- 新增 Graph consistency 风险说明。
- 新增真实数据闭环作为下一阶段重点。

验收标准：

- 文档状态与当前测试输出一致。

## Phase 2：真实 SEC Filing 数据闭环

### 目标

让系统能用真实 ticker 读取 SEC 最新 filing，并生成可追溯 filing evidence。

目标命令：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --year 2024 \
  --no-web \
  --no-transcripts
```

### 任务 2.1：TickerResolver 生产化

当前已有：

```text
src/data/ticker_resolver.py
```

下一步增强：

- 使用 SEC company tickers JSON。
- 支持本地 cache。
- 支持常见 ticker fallback。
- 支持 company name、CIK、ticker 三者统一。
- 给 resolver 增加 provenance metadata。

建议新增或增强 schema：

```python
class CompanyIdentifier(BaseModel):
    ticker: str
    cik: str
    name: str | None = None
    source: Literal["cache", "sec", "fallback"]
    resolved_at: datetime
```

验收标准：

```python
TickerResolver().resolve("AAPL").cik == "0000320193"
TickerResolver().resolve("NVDA").cik == "0001045810"
```

### 任务 2.2：SEC FilingFetcher 真实 10-K/10-Q 拉取

涉及：

```text
src/data/sec_client.py
src/data/filing_fetcher.py
src/pipelines/analyze_company.py
```

要求：

- 根据 ticker resolve CIK。
- 拉取 submissions。
- 选择指定 year 的 10-K；如果无 year，则选择最新 10-K。
- 下载 primary document HTML。
- 转成 `FilingRecord`。
- 至少保留 `full_text`。

验收标准：

```bash
RUN_SEC_INTEGRATION=1 uv run pytest tests/data -m integration
```

以及：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --no-web \
  --no-transcripts
```

能生成基于 SEC filing 的 evidence 和 report。

### 任务 2.3：10-K section parser 增强

当前 parser 是 naive regex。下一步目标是稳定抽取：

- Item 1 Business
- Item 1A Risk Factors
- Item 2 Properties
- Item 7 MD&A
- Item 7A Market Risk
- Exhibit 21，如可用

建议新增：

```text
src/data/sec_sections.py
tests/data/test_sec_sections.py
```

策略：

- HTML anchor 优先。
- 文本 item heading fallback。
- 保留 char offsets。
- 解析失败时保留 `full_text`，不让 pipeline 中断。

验收标准：

- AAPL/NVDA/MSFT 最近 10-K 至少能抽出 `section_1`、`section_1A`、`section_7`。
- section evidence 包含 `section` 和 char offset。

## Phase 3：电话会议真实数据闭环

### 目标

接入至少一个真实 transcript provider，并让 sentiment 和 supply-chain extraction 能处理真实 earnings call。

目标命令：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --no-web \
  --max-transcripts 4
```

### 任务 3.1：选择第一生产 provider

建议优先顺序：

1. FMP，如果已有 API key。
2. Alpha Vantage，如果已有 API key。
3. 公司 IR transcript fallback，后续实现。

涉及：

```text
src/data/providers/fmp.py
src/data/providers/alpha_vantage.py
src/data/transcripts.py
```

要求：

- 无 API key 时 graceful skip。
- 有 API key 时可 list transcripts。
- 可拉取指定 quarter。
- 支持 transcript cache。

验收标准：

```bash
RUN_TRANSCRIPT_INTEGRATION=1 uv run pytest tests/data/providers -m integration
```

### 任务 3.2：Transcript turn normalization

目标：

- 区分 prepared remarks 和 Q&A。
- 区分 CEO/CFO/analyst/operator。
- Analyst question 不能被当作 management claim。
- Operator turn 不进入 sentiment。

涉及：

```text
src/data/transcripts.py
src/agents/transcript_agent.py
src/agents/sentiment_agent.py
```

验收标准：

- 真实 transcript 中 Q&A management answer 可作为 evidence。
- analyst question 只能作为 question context。

### 任务 3.3：管理层情绪升级为 topic-level

输出应包含：

- overall tone
- demand
- margin
- supply chain
- capex
- guidance
- uncertainty
- defensiveness

涉及：

```text
src/schemas/analysis.py
src/agents/sentiment_agent.py
src/pipelines/analyze_sentiment.py
```

验收标准：

- 报告 `Management Sentiment` 不只是一句 tone。
- 每个 topic sentiment 至少有一条 evidence。

## Phase 4：网页搜索生产化

### 目标

把网页搜索从 demo 辅助能力升级成可控、可缓存、可验证的 research source。

### 任务 4.1：SearchRouter provider 配置化

涉及：

```text
src/tools/search_router.py
src/tools/providers/
src/config.py
```

新增配置：

```text
SEARCH_PROVIDER_ORDER=brave,serper,duckduckgo
BRAVE_API_KEY
SERPER_API_KEY
TAVILY_API_KEY
EXA_API_KEY
SERPAPI_API_KEY
```

策略：

- 默认 DuckDuckGo fallback。
- 有 key 时按 provider order 选择。
- 所有搜索结果进入 cache。
- 每个 result 转 Evidence。

验收标准：

```bash
uv run pytest tests/tools/test_search_router.py tests/tools/providers -q
```

### 任务 4.2：网页内容 fetch 和 evidence 精炼

当前 search evidence 主要来自 snippet。正式系统需要 fetch 页面正文并生成更高质量 evidence。

涉及：

```text
src/tools/web_fetch.py
src/tools/search_router.py
src/agents/web_agent.py
```

要求：

- search result snippet 是 weak evidence。
- fetched article paragraph 是 stronger evidence。
- fetch 失败保留 search snippet fallback。
- 每个网页 evidence 保留 URL、title、retrieved_at、published_at。

验收标准：

- `analyze_company --ticker AAPL --max-web-results 5` 至少能生成网页 evidence。
- 动态/403 页面不让 pipeline 崩溃。

## Phase 5：LLM 结构化抽取替换规则 fallback

### 目标

将供应链、政策、风险、机会抽取从 keyword rule 逐步升级为本地 LLM structured output，同时保留规则 fallback。

### 任务 5.1：统一 LLM structured extraction contract

涉及：

```text
src/agents/extraction_agent.py
src/llm/sglang_client.py
src/schemas/
```

要求 LLM 输出：

```json
{
  "entities": [],
  "relations": [],
  "claims": [],
  "evidence": [],
  "warnings": []
}
```

每个 relation/claim 必须带 evidence。

验收标准：

- fake LLM 测试通过。
- 本地 SGLang 不可用时，规则 fallback 仍可运行。

### 任务 5.2：Filing extraction prompt 分 source section 优化

不同 section 使用不同抽取目标：

- Item 1：业务、产品、客户、供应商、竞争、地区。
- Item 1A：风险。
- Item 7：需求、margin、capex、供应链变化。
- Item 7A：汇率、利率、商品风险。

涉及：

```text
src/agents/filing_agent.py
src/agents/extraction_agent.py
```

验收标准：

- 真实 10-K 可抽出 company/product/region/risk。
- 不确定关系不写入 graph。

### 任务 5.3：Transcript extraction prompt 分 speaker 优化

规则：

- Management answer 可生成 claim。
- Analyst question 仅作为上下文。
- CEO/CFO 讲话进入 sentiment 和 strategy claim。

涉及：

```text
src/agents/transcript_agent.py
```

验收标准：

- 真实 transcript 中至少能抽出 demand/margin/supply/capex claim。

## Phase 6：Neo4j 图谱成为核心推理层

### 目标

机会发现不能只读 claim list，必须利用图数据库路径和关系结构。

### 任务 6.1：Graph write integration

目标命令：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --write-graph
```

要求：

- 写入 Company、Product、Region、Risk、Policy、Claim、Evidence。
- 写入 SUPPLIES_TO、EXPOSED_TO、BENEFITS_FROM 等关系。
- 重复运行不产生重复节点。

验收标准：

```bash
RUN_NEO4J_INTEGRATION=1 uv run pytest tests/graph -m integration
```

### 任务 6.2：GraphReasoningAgent

新增：

```text
src/agents/graph_agent.py
tests/agents/test_graph_agent.py
```

能力：

- 查询上游供应商。
- 查询下游客户。
- 查询政策受益公司。
- 查询地缘风险暴露路径。
- 返回 graph paths 给 OpportunityAgent。

验收标准：

- Opportunity hypothesis 包含 `graph_paths`。
- 报告展示至少一条供应链路径。

### 任务 6.3：图算法增强

第一阶段不强制 GDS，但需要封装：

- degree centrality
- path search
- common exposure clustering

后续再接：

- community detection
- link prediction

## Phase 7：风险、政策、地缘政治分析生产化

### 目标

把风险分析从 keyword 分类升级为 evidence-backed exposure model。

### 任务 7.1：Risk taxonomy 标准化

风险类别：

- macro
- policy
- geopolitical
- supply_chain
- customer_concentration
- margin
- legal
- market
- commodity
- currency
- rate
- execution

涉及：

```text
src/schemas/analysis.py
src/agents/risk_agent.py
```

验收标准：

- 每个 risk claim 有 category、score、time_horizon、evidence。

### 任务 7.2：PolicyExposureAgent

政策覆盖：

- IRA
- CHIPS Act
- tariffs
- export controls
- carbon regulation
- defense spending
- antitrust
- tax policy
- reshoring

验收标准：

- 公司可以被标记为 beneficiary/risk/mixed。
- 每个 exposure 带 affected segment。

### 任务 7.3：GeopoliticalExposureAgent

覆盖：

- China/Taiwan
- Middle East
- Red Sea/shipping
- Russia/Ukraine
- export control regions

验收标准：

- 报告展示直接风险和供应链传导风险。
- graph path 可用于解释传导路径。

## Phase 8：机会发现和研究报告升级

### 目标

生成更接近真实研究流程的投资研究假设，而不是模板化段落。

### 任务 8.1：Hypothesis scoring

每条 hypothesis 应包含：

- evidence strength
- graph support
- recency
- counter-evidence strength
- confidence
- next validation questions

涉及：

```text
src/schemas/hypotheses.py
src/agents/opportunity_agent.py
```

验收标准：

- confidence 不只来自 evidence 平均值。
- counter-evidence 会降低 confidence。

### 任务 8.2：Report 增强

报告应展示：

- company overview
- data coverage
- supply chain graph paths
- management sentiment by topic
- policy/geopolitical exposure
- hypotheses
- counter-evidence
- watchlist triggers
- source appendix

涉及：

```text
src/agents/report_agent.py
src/pipelines/generate_report.py
```

验收标准：

- 报告不出现无证据断言。
- 每个 hypothesis 有 supporting evidence 和 counter-evidence 区域。

## Phase 9：评测、回测和质量门禁

### 目标

建立正式项目的持续评测能力。

### 任务 9.1：Extraction eval

建立 golden set：

```text
tests/fixtures/golden/
```

覆盖：

- company entity
- product
- region
- supplier/customer
- risk
- policy

指标：

- entity precision/recall
- relation precision/recall
- unsupported claim rate
- evidence coverage

### 任务 9.2：Report eval

检查：

- disclaimer 存在。
- 无禁用投资建议语言。
- 每条 claim 有 citation。
- source appendix 完整。

### 任务 9.3：Historical backtest scaffold

历史事件：

- CHIPS Act
- IRA
- AI capex cycle
- Red Sea shipping disruption
- export control

目标不是预测股价，而是评估系统是否能在历史时点发现可验证研究假设。

## Phase 10：API 和使用界面

### 目标

在核心 pipeline 稳定后，提供服务层。

### 任务 10.1：FastAPI server

新增：

```text
src/api/server.py
src/api/routes.py
```

接口：

```text
POST /analyze/company
GET /reports/{report_id}
GET /graph/company/{ticker}
GET /evidence/{evidence_id}
```

### 任务 10.2：Job persistence

需要保存：

- analysis request
- report
- evidence
- claims
- graph write status

可先用 DuckDB 或 SQLite。

## 推荐执行顺序

严格按以下顺序推进：

1. 收口当前未提交改动，修 Graph 一致性。
2. 提交当前稳定测试基线。
3. 打通真实 SEC filing：AAPL/NVDA/MSFT。
4. 打通一个 transcript provider。
5. SearchRouter 真实 provider 配置化。
6. LLM structured extraction 接入 filing。
7. LLM structured extraction 接入 transcript。
8. Neo4j 写入真实公司图谱。
9. GraphReasoningAgent 接入 opportunity discovery。
10. 风险/政策/地缘政治 exposure model 升级。
11. Report 升级为正式 research brief。
12. 建立 extraction/report/backtest eval。
13. 最后再做 API server。

## 近期 2 周执行清单

### Week 1

- 修 Graph writer/query/schema 一致性。
- 更新 Step 12 文档状态。
- 提交当前稳定基线。
- 完成 AAPL SEC filing live run。
- 增强 section parser，至少稳定抽 Item 1、1A、7。

### Week 2

- 选择并跑通一个 transcript provider。
- 接入 transcript sentiment topic-level 输出。
- 配置 SearchRouter provider order。
- 将真实 filing/transcript/web evidence 合并进 `analyze_company`。
- 开始 Neo4j integration run。

## 完成定义

本正式执行阶段的第一阶段完成后，应支持：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --year 2024 \
  --max-transcripts 4 \
  --max-web-results 5 \
  --write-graph \
  --output reports/AAPL-2024.md
```

并满足：

- 使用真实 SEC filing。
- 至少一个真实 transcript provider 可选接入。
- 网页 evidence 可选接入。
- 报告中包含供应链、风险、管理层情绪、政策/地缘政治暴露和机会假设。
- 每条结论都有 evidence。
- Neo4j 中可查询公司、claim、evidence 和供应链路径。
- 测试默认全绿。

