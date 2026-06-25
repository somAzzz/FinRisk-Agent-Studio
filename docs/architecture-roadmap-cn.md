# FinText-LLM 架构与路线图规划

## 1. 项目重新定位

FinText-LLM 的目标应从“SEC EDGAR 年报风险抽取工具”升级为：

> 一个本地 LLM 驱动的金融研究 Agent 系统：持续读取年报、电话会议、网页新闻和结构化财务数据，抽取风险、机会、供应链关系和管理层信号，写入图数据库，并生成可追溯证据链的投资研究假设。

这个系统的核心不是单次问答，而是把 filing、transcript、web、graph、agent reasoning 组合成完整研究流程。

## 2. 核心能力目标

### 2.1 公司基本面文本理解

系统需要从 10-K、10-Q、8-K、年报、电话会议和公司官网材料中抽取：

- 公司业务与产品
- 业务分部和收入来源
- 主要客户、供应商、合作伙伴
- 竞争对手
- 地区和产能暴露
- 资本开支和战略变化
- 管理层对需求、成本、利润率和供应链的表述

### 2.2 风险与机会并行发现

当前项目偏向 `risk extraction`，后续应升级为 `risk + opportunity discovery`。

重点问题包括：

- 哪些公司受益于政策补贴、基建支出、能源转型或 AI 资本开支？
- 哪些上游公司会因为下游需求增长而受益？
- 哪些小型公司是大趋势里的“卖铲人”？
- 哪些公司披露了风险，但市场可能尚未充分定价？
- 哪些供应链瓶颈会带来涨价能力或订单外溢？

### 2.3 Agent 化研究流程

本地 LLM 不应只作为一个风险抽取函数，而应成为多 Agent 协作系统。

建议的 Agent 包括：

- `PlannerAgent`：规划研究步骤和工具调用
- `FilingResearchAgent`：阅读年报和 SEC filing
- `TranscriptResearchAgent`：分析电话会议
- `WebResearchAgent`：搜索和抓取网页信息
- `EntityExtractionAgent`：抽取公司、产品、地区、政策、人物等实体
- `RelationExtractionAgent`：抽取客户、供应商、竞争、受益、风险暴露等关系
- `RiskAnalysisAgent`：分析公司、行业、政策、地缘政治风险
- `OpportunityDiscoveryAgent`：发现潜在投资机会
- `SentimentAgent`：分析管理层情绪和语气变化
- `PolicyGeoRiskAgent`：分析政策和地缘政治影响
- `GraphReasoningAgent`：基于图数据库做关系推理
- `CriticAgent`：检查证据不足、幻觉和因果跳跃

### 2.4 供应链图谱和证据链

系统需要把抽取到的实体与关系写入 Neo4j，形成可查询、可推理的供应链图谱。

每一个结论都必须保留证据来源，包括：

- filing 类型、年份、section、原文 quote
- transcript 的 speaker、时间、段落
- 网页 URL、标题、抓取时间
- SEC 或 Hugging Face 数据来源
- LLM 模型名、抽取时间、置信度

## 3. 数据层规划

### 3.1 EDGAR corpus 使用 Hugging Face API

当前 `src/data/loader.py` 默认读取本地 JSONL。后续应改为 Hugging Face streaming-first 方案。

目标接口：

```python
EdgarCorpusLoader(
    dataset="eloukas/edgar-corpus",
    config="year_2020",
    split="train",
    streaming=True,
)
```

设计原则：

- 默认不完整下载数据集到本地。
- 使用 Hugging Face `datasets.load_dataset(..., streaming=True)` 流式读取。
- 原始文本只在必要时缓存。
- 抽取后的结构化结果存入 DuckDB、PostgreSQL 或 SQLite。
- 文本向量写入 Qdrant、LanceDB 或 Chroma。
- 实体关系写入 Neo4j。
- 所有结果保留 `dataset_id + split + row_id + section + char_offset` 引用。

建议新增模块：

```text
src/data/edgar_hf.py
src/data/filing_record.py
src/data/cache.py
```

### 3.2 最新 SEC filing 数据

`eloukas/edgar-corpus` 适合历史语料和回测，但无法覆盖最新 filing。生产系统需要接入 SEC 官方 API。

建议支持：

- SEC Submissions API：公司 filing 历史
- SEC Company Facts API：XBRL 财务事实
- SEC bulk archive：批量更新 company facts 和 submissions
- SEC filing HTML 文本下载与 section extraction

建议新增模块：

```text
src/data/sec_client.py
src/data/filing_fetcher.py
src/data/xbrl_facts.py
```

配置要求：

```text
SEC_USER_AGENT="FinText-LLM contact@example.com"
SEC_RATE_LIMIT=8
```

### 3.3 年报中更有挖掘价值的部分

当前项目重点关注 `section_1A`，但这只是风险披露。更完整的研究应覆盖以下内容：

| 来源 | 价值 | 用途 |
| --- | --- | --- |
| Item 1 Business / `section_1` | 产品、市场、客户、供应链、竞争格局 | 供应链图谱、机会发现 |
| Item 1A Risk Factors / `section_1A` | 公司披露的风险 | 风险分类、风险变化追踪 |
| Item 2 Properties | 工厂、产能、地理位置 | 地缘风险、产能暴露 |
| Item 3 Legal Proceedings | 诉讼和监管事项 | 法律风险 |
| Item 7 MD&A / `section_7` | 管理层对业绩、需求、成本和资本开支的解释 | 管理层情绪、战略变化 |
| Item 7A Market Risk | 利率、汇率、商品价格暴露 | 宏观风险 |
| Item 8 Notes | 客户集中度、收入拆分、债务、长期合同 | 结构化基本面信号 |
| Exhibit 21 | 子公司列表 | 全球实体和地区暴露 |
| XBRL facts | 标准化财务指标 | 文本信号和财务结果对齐 |

重点建议：

- 供应链关系主要从 Item 1、MD&A、Notes、Exhibit 21、网页搜索和电话会议 Q&A 中抽取。
- Risk Factors 更适合作为风险确认来源，而不是供应链发现的唯一来源。

## 4. 电话会议内容规划

电话会议 transcript 是管理层情绪、机会发现和风险验证的重要来源，尤其是 Q&A 部分。

### 4.1 数据源分层

免费或低成本来源：

- Alpha Vantage Earnings Call Transcript API
- Financial Modeling Prep Earnings Transcript API
- 公司 Investor Relations 页面
- Seeking Alpha transcript 页面，需注意使用条款

专业付费来源：

- Quartr API
- Finnhub premium transcripts
- FactSet、S&P Capital IQ、Bloomberg 等机构数据源

建议设计统一接口：

```python
class TranscriptProvider:
    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        ...

    def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
    ) -> Transcript:
        ...
```

实现：

```text
src/data/transcripts.py
src/data/providers/alpha_vantage.py
src/data/providers/fmp.py
src/data/providers/quartr.py
src/data/providers/finnhub.py
src/data/providers/ir_web.py
```

### 4.2 电话会议分析重点

电话会议应拆分为：

- prepared remarks
- Q&A
- CEO 讲话
- CFO 讲话
- analyst question
- management answer

分析维度：

- 乐观、悲观、中性
- 不确定性
- 防御性
- 是否回避问题
- guidance raise/cut/maintain
- demand signal
- margin pressure
- inventory issue
- capex plan
- supply bottleneck
- customer concentration
- policy exposure
- geopolitical exposure

建议输出：

```json
{
  "tone": "positive",
  "uncertainty": 0.31,
  "defensiveness": 0.22,
  "guidance_signal": "raised",
  "topic_sentiment": {
    "demand": "positive",
    "margin": "neutral",
    "supply_chain": "negative",
    "capex": "positive"
  },
  "evidence": []
}
```

## 5. 本地 LLM Agent 系统

### 5.1 Agent Runtime

建议新增：

```text
src/agents/runtime.py
src/agents/state.py
src/agents/memory.py
src/agents/planner.py
```

核心运行流程：

```text
User Goal
  -> PlannerAgent
  -> Tool Selection
  -> Filing / Transcript / Web / Graph Agents
  -> Structured Extraction
  -> Graph Write
  -> Critic Review
  -> Final Research Hypothesis
```

### 5.2 结构化输出标准

所有 Agent 输出都应使用 Pydantic schema。

基础格式：

```json
{
  "claim": "...",
  "entities": [],
  "relations": [],
  "evidence": [],
  "confidence": 0.82,
  "next_actions": []
}
```

证据格式：

```json
{
  "source_type": "10-K",
  "source_id": "AAPL-2024-10K",
  "section": "Item 1",
  "quote": "...",
  "url": "...",
  "retrieved_at": "...",
  "confidence": 0.88
}
```

### 5.3 工具层

建议工具集合：

```text
tools/
├── hf_edgar_stream
├── sec_fetch
├── xbrl_fetch
├── transcript_fetch
├── web_search
├── web_fetch
├── browser_explore
├── vector_search
├── graph_query
├── graph_write
├── financial_metrics
└── citation_store
```

### 5.4 本地模型分工

建议将本地 LLM 分为不同职责：

- embedding model：去重、相似度、召回
- extraction model：实体和关系抽取
- reasoning model：生成假设和推理
- critic model：检查证据和反证
- reranker model：搜索结果排序

## 6. 网页搜索方案优化

当前项目有 DuckDuckGo、`web_fetch` 和 browser exploration，适合原型，但稳定性和可控性不足。

建议引入 `SearchRouter`，根据任务类型选择不同 provider。

### 6.1 免费或低成本方案

| 方案 | 优点 | 缺点 | 建议用途 |
| --- | --- | --- | --- |
| DuckDuckGo / ddgs | 免费、接入快 | 非官方、不稳定、容易变动 | 本地开发和 fallback |
| SEC API | 官方、免费、结构化 | 只覆盖 filing 和 XBRL | filing 主数据源 |
| 公司 IR 页面 | 第一手资料 | 结构不统一 | transcript、presentation、press release |
| Google Programmable Search JSON API | 官方、可控 | 配额有限，需要配置搜索引擎 | 白名单站点搜索 |
| Serper | 低成本 Google SERP | 第三方服务依赖 | 通用新闻和网页搜索 |

### 6.2 付费或生产方案

| 方案 | 优点 | 缺点 | 建议用途 |
| --- | --- | --- | --- |
| Brave Search API | 独立索引，适合通用搜索 | 覆盖和 Google 有差异 | 默认生产搜索 |
| Tavily | 面向 AI Agent/RAG，支持 search/extract/crawl/research | 按 credit 计费，供应商锁定 | Agent 深度搜索 |
| Exa | 语义搜索强，适合找相似公司和主题 | 普通事实检索成本较高 | 机会发现、主题扩展 |
| SerpApi | Google 结果丰富，结构化 SERP，抗 CAPTCHA | 成本较高 | 高价值查询和验证 |

### 6.3 SearchRouter 策略

建议结构：

```text
SearchRouter
├── sec_search
├── ir_search
├── news_search
├── agent_search
├── semantic_search
├── web_fetch
├── browser_explore
└── cache
```

默认策略：

1. filing 和财务数据使用 SEC API。
2. transcript 优先使用 Alpha Vantage、FMP 或 Quartr。
3. 新闻搜索使用 Brave、Serper 或 Tavily。
4. 深度 Agent research 使用 Tavily。
5. 主题和相似公司发现使用 Exa。
6. 高价值验证使用 SerpApi。
7. 所有网页结果必须缓存、去重并保留 evidence。

建议新增：

```text
src/tools/search_router.py
src/tools/providers/brave.py
src/tools/providers/tavily.py
src/tools/providers/exa.py
src/tools/providers/serper.py
src/tools/providers/serpapi.py
src/tools/cache.py
```

## 7. 供应链图数据库规划

### 7.1 Neo4j 图模型

建议节点：

```text
(:Company {cik, ticker, name, sector, industry})
(:Product)
(:Segment)
(:Customer)
(:Supplier)
(:Competitor)
(:Region)
(:Country)
(:Commodity)
(:Policy)
(:Risk)
(:Opportunity)
(:Filing)
(:Transcript)
(:Article)
(:Event)
(:Executive)
(:Claim)
(:Evidence)
```

建议关系：

```text
(:Company)-[:SUPPLIES_TO]->(:Company)
(:Company)-[:BUYS_FROM]->(:Company)
(:Company)-[:CUSTOMER_OF]->(:Company)
(:Company)-[:COMPETES_WITH]->(:Company)
(:Company)-[:HAS_SEGMENT]->(:Segment)
(:Company)-[:SELLS_PRODUCT]->(:Product)
(:Company)-[:DEPENDS_ON]->(:Commodity)
(:Company)-[:EXPOSED_TO]->(:Region)
(:Company)-[:MENTIONS_RISK]->(:Risk)
(:Policy)-[:IMPACTS]->(:Company)
(:Event)-[:IMPACTS]->(:Company)
(:Company)-[:BENEFITS_FROM]->(:Policy)
(:Company)-[:SUBSIDIARY_OF]->(:Company)
(:Claim)-[:SUPPORTED_BY]->(:Evidence)
```

关系属性：

```json
{
  "source_type": "10-K",
  "source_url": "...",
  "filing_year": 2024,
  "section": "Item 1",
  "quote": "...",
  "confidence": 0.82,
  "extracted_at": "...",
  "model": "..."
}
```

### 7.2 供应链发现流程

流程：

1. 从 Item 1、MD&A、Notes、Exhibit 21、transcript 和网页中抽取公司、产品、客户、供应商、地区。
2. 使用 ticker、CIK、公司名、别名做实体归一化。
3. 用网页搜索补充合同、合作、供应、采购、客户案例等证据。
4. 将实体和关系写入 Neo4j。
5. 使用图查询和图算法发现：
   - 二阶供应商
   - 关键瓶颈节点
   - 高中心性上游公司
   - 同一政策受益集群
   - 同一地缘风险暴露集群
   - 潜在 link prediction 关系
6. 用 Opportunity Agent 生成投资假设。
7. 用 Critic Agent 检查证据强度和反证。

### 7.3 机会发现示例

```text
下游：电网投资增长
  -> 多家 utility 在年报和电话会议中提高 grid capex
  -> 供应链图发现 transformer、switchgear、cable、power electronics 上游节点
  -> 网页搜索验证订单、扩产、交付周期和价格上涨
  -> LLM 生成潜在受益公司、证据、风险和下一步验证问题
```

## 8. 风险分析模块

### 8.1 管理层情绪分析

输入：

- MD&A
- earnings call prepared remarks
- earnings call Q&A
- historical transcripts

输出：

```json
{
  "tone": "positive",
  "uncertainty": 0.44,
  "confidence": 0.71,
  "defensiveness": 0.38,
  "guidance_signal": "maintained",
  "topic_sentiment": {
    "demand": "positive",
    "margin": "negative",
    "supply_chain": "neutral",
    "capex": "positive"
  },
  "evidence": []
}
```

重点不是简单情绪分数，而是：

- MD&A 和电话会议是否矛盾。
- prepared remarks 乐观但 Q&A 防御性是否升高。
- 同一主题连续几个季度语气是否恶化。
- 管理层是否回避 analyst 问题。

### 8.2 政策风险和政策机会

覆盖主题：

- IRA / clean energy subsidies
- CHIPS Act
- tariffs
- export controls
- carbon regulation
- defense spending
- healthcare regulation
- antitrust
- tax policy
- reshoring / localization

输出：

```json
{
  "policy": "CHIPS Act",
  "company_exposure": "beneficiary",
  "affected_segments": [],
  "evidence": [],
  "time_horizon": "mid",
  "confidence": 0.78
}
```

### 8.3 地缘政治风险

输入：

- 年报地区收入
- Item 1A 地缘风险披露
- 供应商、工厂、客户地区
- 新闻搜索
- 商品、航运、制裁、冲突事件

输出：

```json
{
  "risk_type": "export_control",
  "region": "China",
  "companies_impacted": [],
  "supply_chain_paths": [],
  "risk_score": 0.73,
  "opportunity_offset": []
}
```

分析重点：

- 哪些公司直接受冲突、制裁、出口管制影响。
- 哪些公司间接受供应链传导影响。
- 哪些替代供应商或地区会受益。
- 哪些风险已经在公司年报里持续披露但网页新闻最近升温。

## 9. 推荐项目结构

```text
src/
├── agents/
│   ├── runtime.py
│   ├── planner.py
│   ├── filing_agent.py
│   ├── transcript_agent.py
│   ├── web_agent.py
│   ├── graph_agent.py
│   ├── risk_agent.py
│   ├── opportunity_agent.py
│   ├── sentiment_agent.py
│   └── critic_agent.py
├── data/
│   ├── edgar_hf.py
│   ├── sec_client.py
│   ├── transcripts.py
│   ├── xbrl.py
│   └── entity_resolver.py
├── graph/
│   ├── schema.cypher
│   ├── writer.py
│   ├── queries.py
│   └── algorithms.py
├── tools/
│   ├── search_router.py
│   ├── providers/
│   │   ├── brave.py
│   │   ├── tavily.py
│   │   ├── exa.py
│   │   ├── serper.py
│   │   └── serpapi.py
│   ├── web_fetch.py
│   └── browser.py
├── pipelines/
│   ├── ingest_filings.py
│   ├── ingest_transcripts.py
│   ├── extract_entities.py
│   ├── build_supply_graph.py
│   ├── analyze_company.py
│   └── discover_opportunities.py
├── evaluation/
│   ├── extraction_eval.py
│   ├── graph_eval.py
│   └── backtest.py
└── api/
    ├── server.py
    └── routes.py
```

## 10. 分阶段实施路线图

### Phase 0：整理当前原型

目标：保留已有代码，但拆清边界。

- 将 `loader.py` 改造成数据接口，不再绑定本地路径。
- 保留 `web_fetch`、`web_search`、`browser`，但统一接入 `SearchRouter`。
- 给所有 LLM 输出改成 Pydantic schema。
- 加入 evidence/citation 数据结构。
- 修正硬编码日期、模型名、路径。

### Phase 1：数据层升级

- 接入 Hugging Face streaming 读取 `eloukas/edgar-corpus`。
- 接入 SEC API 获取最新 filing。
- 接入 Alpha Vantage 或 FMP 获取 transcript。
- 用 DuckDB 存公司、filing metadata、transcript metadata。
- 建立 entity resolver，统一公司名、ticker、CIK 和别名。

### Phase 2：Agent Runtime

- 实现 Planner、ToolRouter、Memory。
- 每个 Agent 只做一类任务。
- 所有输出必须带 evidence。
- 加入 Critic Agent，禁止无证据结论进入最终报告。

### Phase 3：抽取模块

年报抽取：

- business segments
- products
- customers
- suppliers
- competitors
- regions
- risks
- opportunities

电话会议抽取：

- sentiment
- guidance
- demand
- margin
- capex
- supply chain

网页抽取：

- recent events
- contracts
- partnerships
- policy impact
- news impact

### Phase 4：Neo4j 供应链图

- 设计 Neo4j schema。
- 写入公司、产品、地区、政策、风险、机会。
- 实现实体合并和边置信度。
- 支持图查询：
  - 找某公司上游
  - 找某公司下游客户
  - 找某政策受益公司
  - 找某风险暴露路径
  - 找二阶供应链机会
- 引入 centrality、community、link prediction 等图算法。

### Phase 5：投资研究假设生成

每个 hypothesis 结构：

```json
{
  "title": "...",
  "type": "supply_chain_opportunity",
  "companies": [],
  "graph_paths": [],
  "evidence": [],
  "counter_evidence": [],
  "confidence": 0.74,
  "watchlist_triggers": [],
  "not_investment_advice": true
}
```

注意：系统生成的是研究假设和 watchlist，不应表述为确定性投资建议。

### Phase 6：评测和回测

- 抽取准确率评测。
- 图关系人工抽样验证。
- 搜索结果质量评测。
- Agent hallucination rate 评测。
- 历史事件回测：
  - CHIPS Act
  - IRA
  - AI capex cycle
  - supply disruption
  - defense spending cycle

## 11. MVP 建议

建议第一个可落地 MVP 聚焦一个闭环：

> 输入一个 ticker，系统读取最新 10-K、最近 4 次电话会议和最近网页信息，抽取供应链、风险、政策暴露和管理层情绪，写入 Neo4j，并输出 3-5 条带证据的风险或机会假设。

MVP 输入：

```text
AAPL
```

MVP 输出：

```text
1. 供应链路径
2. 主要上游依赖
3. 管理层情绪变化
4. 政策/地缘政治风险
5. 潜在受益或受损公司
6. 每条结论对应证据
```

## 12. 近期优先级

建议按以下顺序推进：

1. 重构 `loader.py`，实现 Hugging Face streaming loader。
2. 增加 SEC API client。
3. 增加 transcript provider 抽象，先实现 Alpha Vantage 或 FMP。
4. 定义统一 Evidence、Entity、Relation、Claim schema。
5. 实现 SearchRouter 和搜索缓存。
6. 实现 Neo4j schema 和 graph writer。
7. 实现 Filing Agent 和 Transcript Agent。
8. 实现供应链关系抽取。
9. 实现 Opportunity Agent 和 Critic Agent。
10. 做第一个 ticker 级别端到端 demo。

## 13. 总结

FinText-LLM 后续应朝着“证据可追溯的本地金融研究 Agent 系统”演进。

短期重点不是堆更多单点功能，而是建立统一抽象：

- 数据源统一
- LLM 输出统一
- 证据结构统一
- 工具调用统一
- 实体关系统一
- 图数据库统一

当这些基础设施稳定后，风险分析、机会发现、管理层情绪、政策风险和地缘政治风险都可以作为 Agent 插件持续扩展。
