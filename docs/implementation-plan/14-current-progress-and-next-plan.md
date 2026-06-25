# Step 14 - 最近提交复盘、当前进度与下一步执行方案

## 目标

本文件基于最近两个本地 Git 提交，对 FinText-LLM 当前实现状态重新评估，并给出下一阶段的实际执行方案。

本步骤不是重新设计系统，而是回答三个问题：

- 最近提交已经把项目推进到了哪里？
- 当前代码距离正式项目目标还差什么？
- 下一步应按什么顺序执行，才能避免继续堆叠半成品功能？

## 最近提交复盘

当前本地 `main` 最新提交为：

```text
9248c02 feat(step13): production roadmap phases 1-4 — Neo4j dual-key, ticker provenance, section parser, search provider config
f415b80 feat(step12): stabilization — pytest config, browser cleanup, ticker resolver, supply-chain extraction, dedupe, sentiment lexicons
0273859 origin/main Add FinText roadmap implementation plan
```

这说明本地代码已经领先远程 `origin/main` 两个提交。后续如果要让其它编程助手接手，应先完成质量检查并 push 到远程。

### `f415b80` 的实际推进

该提交主要完成 Step 12 稳定化工作：

- pytest 默认入口修复，`uv run pytest -q` 可以直接运行。
- `BrowserWrapper` 在缺少 `agent-browser` 时可以优雅降级。
- Slack token sanitizer 测试与实际规则对齐。
- 报告 evidence 做了基于 `evidence_id` 的去重。
- 增加规则型供应链抽取，使 offline demo 能生成 `Supply Chain Map`。
- 增强管理层情绪和机会发现的词典规则。

该提交的价值是把项目从“骨架很多但测试不稳”推进到“离线链路可验证”。

### `9248c02` 的实际推进

该提交开始进入正式生产化基础建设：

- 增强 Neo4j 写入字段一致性，避免 `entity_id`、`claim_id`、`evidence_id` 在写入和读回时丢失语义。
- 增强 ticker resolver，加入 provenance 相关信息。
- 新增 SEC section parser，为真实 10-K / 10-Q section-level evidence 做准备。
- 增强 SearchRouter provider 配置，为免费/付费搜索 provider 切换做准备。
- 增加对应测试，扩大生产化模块覆盖。

该提交的价值是把项目从“离线 demo”推进到“真实数据闭环的前置基础”。

## 当前验证基线

当前测试基线：

```bash
uv run pytest -q
```

结果：

```text
368 passed, 1 skipped, 6 warnings
```

当前离线 demo 可运行：

```bash
uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

离线 demo 已能生成：

- 公司研究报告
- 风险和机会假设
- 供应链关系
- 管理层情绪
- evidence/source 引用

## 当前项目进度判断

### 已完成

项目已经完成以下基础能力：

- 分层目录和 Python 包结构。
- Pydantic schema 骨架。
- Hugging Face EDGAR loader 初版。
- SEC client 和 filing fetcher 初版。
- transcript provider 抽象。
- SearchRouter 和搜索缓存初版。
- 本地 LLM / SGLang client 抽象。
- agent runtime 骨架。
- 风险、机会、情绪、报告 agent 初版。
- 规则型供应链抽取。
- Neo4j writer/query 初版。
- offline fixture demo。
- pytest 测试基线。
- 分步实施文档。

### 部分完成

以下能力已经有实现，但还不能视为正式完成：

- SEC filing 真实拉取：代码已有，但需要用真实 ticker 做端到端验证。
- SEC section parser：已有初版，但需要覆盖更多真实 10-K 样本。
- transcript ingestion：抽象已有，但真实 provider、缓存、失败处理和 schema 还需补齐。
- web search：provider 路由已有，但免费/付费策略、网页正文抽取、证据评分还未生产化。
- supply chain extraction：当前规则能跑，但需要 LLM 结构化抽取和图数据库推理增强。
- sentiment analysis：当前能输出方向，但还缺少 topic-level、speaker-level 和时间序列能力。
- policy/geopolitical risk：框架已有，但 demo 中仍基本为空。
- Neo4j graph：写入和查询初版可用，但还没有形成 graph-based opportunity discovery。

### 尚未完成

以下是正式项目目标中的关键缺口：

- 真实公司一键分析闭环。
- 电话会议真实数据闭环。
- 网页搜索证据质量控制。
- 本地 LLM agent 系统的多 agent 协作。
- 结构化 LLM 抽取替代规则 fallback。
- 供应链上下游图谱自动发现。
- 基于图路径的潜在投资方向发现。
- 管理层情绪、政策风险、地缘政治风险的统一评分。
- 历史回测和报告质量评估。
- API / UI 服务层。

## 当前主要风险

### 风险 1：本地提交尚未同步远程

当前本地 `main` 领先 `origin/main`。如果其它助手从远程仓库拉代码，会缺少 Step 12 和 Step 13 的实际实现。

处理方式：

```bash
git status --short
uv run pytest -q
git push origin main
```

### 风险 2：Ruff 仍有真实代码问题

当前测试已经通过，但局部 ruff 仍暴露出需要优先处理的问题：

- `src/data/filing_fetcher.py` 存在重复 `__init__` 定义。
- `src/tools/search_router.py` 存在重复或未使用导入。
- `src/data/sec_sections.py` 存在非 ASCII 正则字符、导入风格和导出顺序问题。
- `datetime.utcnow()` 有 deprecation warning。

复杂度类问题可以后置，不应在当前阶段大规模重构 agent 和 pipeline。

### 风险 3：真实数据闭环尚未验证

当前离线 demo 可以跑通，但正式目标要求真实 ticker 能自动完成：

- resolve ticker / CIK
- 拉取 SEC filing
- 解析 filing sections
- 生成 evidence
- 抽取风险、机会、供应链
- 可选写入 Neo4j
- 输出带证据链报告

因此下一阶段重点应从 fixture 转向真实 `AAPL`、`MSFT`、`NVDA`。

### 风险 4：报告还有语义重复

报告已经基于 `evidence_id` 去重，但仍可能出现同一网页证据以不同句子或不同 agent 输出重复进入报告。

后续需要增加 semantic-level 去重：

- 按 source URL 归并。
- 按 normalized sentence 归并。
- 按 claim/evidence 相似度归并。
- 在 report agent 层限制同一 source 的重复引用。

### 风险 5：规则抽取容易形成能力上限

当前供应链、情绪、机会发现主要依赖规则和词典。规则适合兜底，但不能承担正式项目的核心推理。

后续必须引入本地 LLM structured extraction：

- filing extraction agent
- transcript extraction agent
- web evidence extraction agent
- supply-chain relation agent
- opportunity hypothesis agent
- critic / verifier agent

## 下一步执行方案

## Phase A：质量收口和远程同步

### 目标

把当前本地实现整理成其它助手可以安全接手的基线。

### 任务 A1：修复高优先级 ruff 问题

涉及文件：

```text
src/data/filing_fetcher.py
src/data/sec_sections.py
src/tools/search_router.py
src/tools/providers/base.py
src/tools/providers/brave.py
```

执行要求：

- 修复 `filing_fetcher.py` 重复 `__init__`。
- 清理 `search_router.py` 未使用或重复导入。
- 将 `sec_sections.py` 中容易混淆的 dash 字符改成明确 ASCII 或 escaped unicode。
- 将 `datetime.utcnow()` 改成 timezone-aware 写法。
- 暂不处理复杂度类 lint，避免引入无关重构。

验收命令：

```bash
uv run pytest -q
uv run ruff check src/schemas src/data src/agents src/graph src/pipelines src/tools/search_router.py src/tools/search_cache.py
```

### 任务 A2：更新文档中的测试基线

涉及文件：

```text
docs/implementation-plan/12-stabilization-and-next-steps.md
docs/implementation-plan/13-production-execution-roadmap.md
```

执行要求：

- 将旧的测试结果更新为当前真实结果。
- 明确 Step 12 已完成的项目。
- 明确剩余问题转入 Step 14。

### 任务 A3：同步远程

执行要求：

```bash
git status --short
uv run pytest -q
git push origin main
```

验收标准：

- `origin/main` 与本地 `main` 对齐。
- 其它助手从远程 clone 后可以看到 Step 12、Step 13 和 Step 14。

## Phase B：真实 SEC Filing 闭环

### 目标

实现第一个真实公司 filing-only 分析闭环。

目标命令：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --no-web \
  --no-transcripts
```

### 任务 B1：验证 ticker / CIK resolve

目标：

- `AAPL` -> `0000320193`
- `MSFT` -> `0000789019`
- `NVDA` -> `0001045810`

要求：

- resolver 输出 provenance。
- 缓存命中和 SEC 远程命中都可区分。
- 失败时返回清晰错误，不让 pipeline 静默 fallback 到错误公司。

### 任务 B2：验证 SEC filing fetcher

要求：

- 能选择最新 10-K。
- 能按 year 选择 10-K。
- 能下载 primary document。
- 能转换成 `FilingRecord`。
- 能保留 accession number、form type、filing date、source URL。

建议增加可选 integration test：

```bash
RUN_SEC_INTEGRATION=1 uv run pytest tests/data -m integration
```

### 任务 B3：增强 section evidence

要求至少抽取：

- Item 1 Business
- Item 1A Risk Factors
- Item 7 MD&A
- Item 7A Market Risk

每个 section evidence 应包含：

- section name
- source filing
- char offset
- text snippet
- evidence id

## Phase C：电话会议真实数据闭环

### 目标

将 transcript 从抽象接口推进到真实 provider 可用。

### Provider 决策

优先比较：

- FMP：覆盖较好，付费后稳定性较高。
- Alpha Vantage：门槛低，但覆盖和限流需要验证。
- Finnhub：适合新闻和部分 transcript 数据，付费能力更完整。
- Polygon / FactSet / Refinitiv：更生产化，但成本更高。

短期建议：

- 免费或低成本验证阶段：Alpha Vantage / FMP。
- 正式生产阶段：FMP + 备用 provider，或商业数据源。

### 任务 C1：Transcript schema 收口

要求区分：

- prepared remarks
- Q&A
- speaker
- role
- quarter / fiscal year
- call date
- source provider

### 任务 C2：管理层情绪升级

要求：

- prepared remarks 和 Q&A 分开评分。
- CFO / CEO / analyst question 分开记录。
- 输出 tone shift。
- 所有情绪判断必须引用 transcript evidence。

## Phase D：网页搜索和证据质量生产化

### 目标

让网页搜索成为可控证据来源，而不是简单搜索结果拼接。

### 免费方案

可用来源：

- DuckDuckGo
- SEC
- company investor relations
- company press release
- government / regulator website

优点：

- 成本低。
- 适合开发和 fallback。

缺点：

- 稳定性不可控。
- 召回和排序不可控。
- 速率限制和反爬风险较高。

### 付费方案

候选：

- Brave Search API
- Tavily
- Serper
- Exa
- Bing Web Search

优点：

- 稳定性更好。
- 可控参数更多。
- 更适合批量分析。

缺点：

- 成本上升。
- 不同 provider 的结果偏差需要评估。

### 任务 D1：SearchRouter 策略化

要求：

- 支持 provider priority。
- 支持按查询类型选择 provider。
- 支持失败 fallback。
- 支持结果缓存和去重。

查询类型至少包括：

- supply chain
- customer / supplier
- policy risk
- geopolitical risk
- management change
- product demand
- litigation / regulation

### 任务 D2：网页正文 evidence

要求：

- 不只保存 search result snippet。
- 对高价值结果 fetch 正文。
- 抽取正文段落。
- 记录 URL、标题、发布时间、抓取时间。
- 对段落进行 relevance scoring。

## Phase E：本地 LLM Agent 系统

### 目标

把当前规则型 pipeline 升级为可控的多 agent 系统。

### Agent 设计

建议拆分：

- `FilingAnalysisAgent`
- `TranscriptAnalysisAgent`
- `WebEvidenceAgent`
- `SupplyChainAgent`
- `RiskAgent`
- `PolicyGeoAgent`
- `OpportunityAgent`
- `GraphReasoningAgent`
- `ReportAgent`
- `CriticAgent`

### 执行原则

- LLM 输出必须是结构化 JSON。
- 所有 claim 必须绑定 evidence。
- agent 之间通过 schema 传递数据，不直接拼接自然语言。
- rule-based extractor 保留为 fallback。
- critic agent 负责过滤 unsupported claim。

## Phase F：Neo4j 图谱推理

### 目标

将供应链和机会发现从列表逻辑升级为图谱推理。

### 图谱节点

至少包括：

- Company
- Product
- Segment
- Supplier
- Customer
- Region
- Policy
- Risk
- Opportunity
- Evidence
- Claim

### 图谱关系

至少包括：

- SUPPLIES_TO
- CUSTOMER_OF
- COMPETES_WITH
- EXPOSED_TO
- BENEFITS_FROM
- SUPPORTS
- CONTRADICTS
- MENTIONS

### 任务 F1：真实数据写图

目标命令：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --write-graph
```

验收标准：

- Neo4j 中能看到 company、evidence、claim、supply-chain relation。
- 查询能读回 claim evidence。
- 报告能引用 graph path。

### 任务 F2：潜在投资方向发现

图推理示例：

- 上游供应商集中度高，且需求加速。
- 某地区政策变化影响多个客户行业。
- 某供应链瓶颈同时暴露多个上市公司。
- 管理层对同一业务线语气改善，且客户网页数据支持需求增长。

输出必须包含：

- hypothesis
- supporting graph path
- supporting evidence
- counter evidence
- confidence

## Phase G：政策、地缘政治和管理层情绪集成

### 目标

让报告不只包含公司内部风险，也能覆盖外部环境变化。

### 数据来源

- SEC risk factor
- transcript Q&A
- government / regulator websites
- news search
- sanctions / export control lists
- company geographic revenue disclosure

### 输出

每家公司至少输出：

- policy exposure
- geopolitical exposure
- region-level risk
- regulation-sensitive product / segment
- management tone by topic
- trend vs prior period

## Phase H：评估、回测和报告产品化

### 目标

让系统输出可以被验证，而不是只生成看起来合理的文本。

### 任务 H1：Extraction eval

建立 golden dataset：

- 供应链关系
- 风险条目
- 机会条目
- 政策风险
- 地缘风险

指标：

- precision
- recall
- evidence support rate
- unsupported claim rate

### 任务 H2：Report eval

指标：

- evidence coverage
- duplicate evidence rate
- unsupported claim count
- source diversity
- graph path usage rate

### 任务 H3：Historical case backtest

选择历史案例：

- 半导体出口管制
- AI data center demand
- EV battery supply chain
- GLP-1 药物供应链
- 能源价格冲击

验证系统是否能在当时可见信息中提出合理 hypothesis。

## 建议执行顺序

下一步不要同时展开所有方向。建议按以下顺序推进：

1. Phase A：质量收口和远程同步。
2. Phase B：真实 SEC filing-only 闭环。
3. Phase C：电话会议真实数据闭环。
4. Phase D：网页搜索证据质量生产化。
5. Phase E：本地 LLM structured extraction agent。
6. Phase F：Neo4j 图谱推理。
7. Phase G：政策、地缘政治和管理层情绪集成。
8. Phase H：评估、回测和报告产品化。

## 两周内建议完成的具体事项

### 第 1-2 天

- 修复高优先级 ruff 问题。
- 更新 Step 12 / Step 13 中过期测试状态。
- push 当前本地提交到 remote。

### 第 3-5 天

- 跑通 `AAPL --no-web --no-transcripts`。
- 增加 SEC integration test。
- 强化 section parser。

### 第 6-8 天

- 选择 transcript provider。
- 接入至少一个真实 transcript 来源。
- 输出 prepared remarks / Q&A 分离情绪。

### 第 9-11 天

- 完成 SearchRouter provider priority。
- 增加网页正文抓取和段落 evidence。
- 针对供应链、政策、地缘风险设计 query templates。

### 第 12-14 天

- 接入本地 LLM structured extraction。
- 增加 critic agent。
- 将供应链关系写入 Neo4j。
- 生成第一份真实 ticker 的 evidence-backed graph report。

## 下一阶段完成定义

当以下命令可以稳定运行时，认为下一阶段完成：

```bash
uv run python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --year 2024 \
  --write-graph
```

输出报告必须包含：

- filing section evidence
- transcript evidence
- web evidence
- supply-chain graph path
- management sentiment
- policy risk
- geopolitical risk
- opportunity hypotheses
- counter evidence
- confidence score

并且满足：

- `uv run pytest -q` 全绿。
- 高优先级 ruff 问题清零。
- 真实 integration test 可通过环境变量开启。
- 所有最终 claim 都有 evidence。
- Neo4j 中可以查询到 company -> claim -> evidence，以及 company -> supplier/customer -> risk/opportunity 路径。
