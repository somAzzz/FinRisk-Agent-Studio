# 08 - Production Hardening 与真实数据工程化方案

## 目标

本文件是在当前 v18 实现审查后的修正方案。当前 v18 已经完成：

- Pydantic schema。
- fixture-driven workflow。
- Sankey payload。
- recursive expansion。
- FastAPI routes。
- 前端 Sankey 组件。
- 单元测试、API 测试、前端测试。

但当前实现仍主要是 demo skeleton，不是完整工程化产品。核心问题：

> OpenAI / ChatGPT 供应链可以稳定演示，但主要来自 fixture / in-memory fallback；真实搜索、LLM 结构化抽取、Neo4j 持久化、后台任务、前端主入口、生产质量评估和观测性还没有成为主路径。

本文件目标：

> 把 v18 从 demo acceptance 升级为 production-grade Product Supply Chain Explorer。

## 当前审查结果

已验证通过：

```bash
uv run pytest -q
# 608 passed, 7 skipped

uv run pytest tests/supply_chain tests/api/test_supply_chain_api.py tests/graph/test_supply_chain_queries.py -q
# 46 passed

uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api src/supply_chain
# All checks passed

cd frontend && npm test -- --run
# 31 passed

cd frontend && npm run build
# passed

uv run python -m src.supply_chain.workflow --company OpenAI --product ChatGPT --max-depth 3 --demo-mode
# completed, nodes=19, links=17, evidence=12
```

主要差距：

1. `RequirementDecomposerStep` real mode 尚未实现，仍 fallback 到 fixture。
2. `SupplierDiscoveryStep` real mode 尚未实现，未真正接入 `SearchRouter`。
3. `GraphBuilderStep` 尚未写入 Neo4j，仍是 in-memory graph。
4. `/supply-chain/explore` 返回 202，但实际同步执行 workflow。
5. `SupplyChainExplorer` 组件存在，但尚未接入主 `App.tsx` 产品入口。
6. `SupplyChainEvaluation.final_status` 复用 workflow status，语义不适合作为质量评估结果。
7. 缺少 provider observability、run persistence、cache policy、rate limit、retry、timeout、成本控制。
8. 全仓 ruff 仍未归零，虽然核心目录已通过。

## Production Definition of Done

Production-ready v18 必须满足：

```text
真实数据路径可运行
后台任务不阻塞请求
结果可持久化
供应链边可追溯 evidence
Neo4j 可写入/读取
前端有正式入口
点击节点可递归探索真实数据
评估结果语义明确
失败可观测、可重试、可降级
CI 覆盖核心路径
```

最低生产验收案例：

```text
OpenAI + ChatGPT
→ real/cached SearchRouter discovery
→ evidence-backed Sankey
→ click CPU
→ recursive real/cached expansion
→ write graph
→ retrieve graph
→ frontend renders merged Sankey
→ evaluation pass or needs_review with reasons
```

## Phase 1：评估语义与状态模型修正

### 问题

当前：

```python
SupplyChainEvaluation.final_status: SupplyChainStatus = "completed"
```

这把 workflow lifecycle 和 quality verdict 混在一起。

### 修改目标

新增独立 verdict：

```python
EvaluationVerdict = Literal["pass", "needs_review", "fail"]
```

修改：

```python
class SupplyChainEvaluation(BaseModel):
    final_status: EvaluationVerdict
    schema_valid: bool
    graph_connected: bool
    acyclic_for_sankey: bool
    confirmed_edges_have_evidence: bool
    unsupported_edges: list[str]
    low_confidence_edges: list[str]
    source_diversity_score: float
    human_review_required: bool
```

workflow status 仍保留：

```python
SupplyChainExploreState.status: queued | running | completed | failed | needs_review
```

映射规则：

```text
evaluation.pass → workflow completed
evaluation.needs_review → workflow needs_review
evaluation.fail → workflow failed
```

### 涉及文件

```text
src/supply_chain/models.py
src/supply_chain/sankey.py
src/supply_chain/steps/evaluator.py
src/api/supply_chain.py
frontend/src/supply-chain-types.ts
frontend/src/components/SupplyChainNodeDrawer.tsx
tests/supply_chain/test_models.py
tests/supply_chain/test_evaluator.py
tests/api/test_supply_chain_api.py
frontend/src/components/SupplyChainExplorer.test.tsx
```

### 验收

```bash
uv run pytest tests/supply_chain/test_models.py tests/supply_chain/test_evaluator.py -q
uv run pytest tests/api/test_supply_chain_api.py -q
cd frontend && npm test -- --run SupplyChainExplorer
```

必须断言：

- valid fixture `final_status == "pass"`。
- unsupported confirmed edge `final_status == "fail"`。
- hypothesized edge without evidence `final_status == "needs_review"`。

## Phase 2：真实 Requirement Decomposer

### 问题

当前 `SupplyChainRequirementDecomposerStep` 只读 fixture。real mode 未做产品需求拆解。

### 修改目标

实现三层 decomposer：

```text
Rule decomposer
→ LLM structured decomposer
→ cached/fixture fallback
```

接口：

```python
class RequirementDecomposer(Protocol):
    async def decompose(
        self,
        request: SupplyChainExploreRequest,
        context: ProductContext,
    ) -> RequirementDecomposition:
        ...
```

输出：

```python
class RequirementItem(BaseModel):
    requirement_id: str
    label: str
    node_type: Literal["component", "service", "commodity", "infrastructure", "energy"]
    importance: float
    confidence: float
    rationale: str
    evidence_ids: list[str] = []
```

OpenAI / ChatGPT real mode 至少应拆出：

```text
cloud compute
GPU accelerator
CPU/server platform
HBM memory
networking
data center power
data center facility
model/data licensing
```

### LLM 要求

- 输出必须通过 Pydantic validate。
- JSON invalid 时 fallback 到 rule decomposer。
- LLM 不得直接生成 confirmed supplier edge，只能生成 requirement nodes。
- 所有 LLM 输出记录 prompt version 和 model。

### 涉及文件

```text
src/supply_chain/prompts.py
src/supply_chain/steps/requirement_decomposer.py
src/supply_chain/models.py
src/llm/client.py
tests/supply_chain/test_requirement_decomposer.py
```

### 验收

```bash
uv run pytest tests/supply_chain/test_requirement_decomposer.py -q
```

必须覆盖：

- rule decomposer 对 ChatGPT 产生核心需求。
- mock LLM 返回合法 JSON 后生成需求节点。
- mock LLM 返回非法 JSON 后 fallback。
- unknown product 不返回空图，至少生成 `needs_review` requirement。

## Phase 3：真实 Supplier Discovery

### 问题

当前 `SupplyChainSupplierDiscoveryStep` real mode 只记录：

```text
real mode not yet implemented; using fixture
```

### 修改目标

接入 `SearchRouter`，并实现 supplier relation extraction。

流程：

```text
Requirement node
→ query generation
→ SearchRouter
→ optional WebFetch / Browser
→ supplier relation extractor
→ evidence normalizer
→ edge creation
```

### Search Intent 扩展

确认并补齐：

```text
product_supply_chain
supplier_discovery
component_supplier
cloud_dependency
datacenter_power
semiconductor_supply_chain
```

查询模板：

```text
{company} {product} {requirement} supplier evidence
{product} upstream {requirement} suppliers official announcement
{requirement} major suppliers manufacturers companies market share
{company} {product} depends on {requirement}
```

### ExtractedSupplierRelation

新增：

```python
class ExtractedSupplierRelation(BaseModel):
    requirement_node_id: str
    supplier_company: str
    supplier_ticker: str | None
    relation_type: RelationType
    evidence_quote: str
    source_url: str | None
    source_title: str | None
    confidence: float
    source_quality: float
    is_confirmed: bool
    uncertainty: str
```

Confirmed edge 规则：

```text
source_url exists
evidence_quote length >= min threshold
confidence >= 0.6
source_quality >= 0.5
```

否则：

```text
relation_type = hypothesized
evaluation.needs_review
```

### 涉及文件

```text
src/supply_chain/steps/supplier_discovery.py
src/supply_chain/evidence.py
src/supply_chain/models.py
src/tools/search_router.py
src/tools/providers/base.py
tests/supply_chain/test_supplier_discovery.py
tests/supply_chain/test_evidence_normalizer.py
```

### 验收

```bash
uv run pytest tests/supply_chain/test_supplier_discovery.py tests/supply_chain/test_evidence_normalizer.py -q
```

必须覆盖：

- mock SearchRouter 返回 NVIDIA 后生成 `component:gpu-accelerator -> company:nvidia`。
- mock SearchRouter 返回 Microsoft Azure 后生成 cloud edge。
- search failure 写入 fallback event。
- empty evidence 不产生 confirmed edge。
- low confidence relation 进入 hypothesized。

## Phase 4：Neo4j Graph Persistence

### 问题

当前 `GraphBuilderStep` 只保留 state in-memory。

### 修改目标

新增生产图写入路径：

```text
state.nodes / state.links / state.evidence
→ GraphWriter or SupplyChainGraphWriter
→ Neo4j
→ SupplyChainQueries
→ SankeyPayload
```

建议新增：

```text
src/graph/supply_chain_writer.py
```

职责：

- label mapping。
- relation mapping。
- idempotent MERGE。
- evidence node write。
- claim/evidence relation write。
- edge evidence relation write。

### Neo4j Schema

补齐：

```cypher
Component(entity_id)
Service(entity_id)
Infrastructure(entity_id)
EnergySource(entity_id)
DataCenter(entity_id)
```

关系：

```text
OFFERS
REQUIRES
SUPPLIED_BY
MANUFACTURED_BY
HOSTED_ON
POWERED_BY
ENABLED_BY
DEPENDS_ON
SUPPORTED_BY
```

### Runtime 策略

配置：

```text
SUPPLY_CHAIN_GRAPH_BACKEND=memory|neo4j
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=
```

行为：

- `memory`：用于 tests/demo。
- `neo4j`：生产写入。
- Neo4j 不可用：fallback to memory + warning。

### 涉及文件

```text
src/graph/schema.cypher
src/graph/supply_chain_writer.py
src/graph/supply_chain_queries.py
src/supply_chain/steps/graph_builder.py
src/config.py
tests/graph/test_supply_chain_writer.py
tests/graph/test_supply_chain_queries.py
tests/supply_chain/test_graph_builder.py
```

### 验收

```bash
uv run pytest tests/graph/test_supply_chain_writer.py tests/graph/test_supply_chain_queries.py -q
uv run pytest tests/supply_chain/test_graph_builder.py -q
```

Integration：

```bash
RUN_NEO4J_INTEGRATION=1 uv run pytest tests/graph -m integration -q
```

## Phase 5：后台任务、Run Persistence 与 API 生产化

### 问题

当前：

```text
POST /supply-chain/explore
→ await run_supply_chain_workflow(request)
→ 同步返回
```

真实搜索/LLM/browser 接入后会阻塞请求。

### 修改目标

实现异步后台运行：

```text
POST /supply-chain/explore
→ create run
→ status=queued
→ background task
→ GET status polling
→ GET sankey after completion
```

### Run Store

第一阶段：

```text
InMemorySupplyChainRunStore
```

第二阶段：

```text
SQLiteSupplyChainRunStore
```

接口：

```python
class SupplyChainRunStore(Protocol):
    async def create(request) -> SupplyChainExploreState: ...
    async def get(run_id) -> SupplyChainExploreState | None: ...
    async def update(state) -> None: ...
    async def list(limit, offset) -> list[RunSummary]: ...
```

### API 行为

`POST /explore`：

```json
{
  "run_id": "...",
  "status": "queued",
  "sankey_url": "/supply-chain/{run_id}/sankey"
}
```

`GET /{run_id}`：

```json
{
  "status": "running",
  "current_step": "supplier_discovery",
  "progress": 0.42
}
```

`GET /{run_id}/sankey`：

- running：返回 202 或 partial payload。
- completed：返回 full payload。
- failed：返回 error + findings。

### 涉及文件

```text
src/api/supply_chain.py
src/api/run_store.py
src/supply_chain/workflow.py
tests/api/test_supply_chain_api.py
```

### 验收

```bash
uv run pytest tests/api/test_supply_chain_api.py -q
```

必须覆盖：

- POST 后立即返回 queued。
- background disabled 时测试可手动推进。
- unknown run 404。
- failed run 可查询 error。
- expansion 使用 parent run，不污染 parent state 除非明确 merge。

## Phase 6：前端产品化入口与交互

### 问题

`SupplyChainExplorer` 组件存在，但主 `App.tsx` 仍只展示 FinRisk workflow。

### 修改目标

新增应用级导航：

```text
Risk Intelligence
Product Supply Chain
```

或：

```text
Tabs:
- FinRisk Workflow
- Supply Chain Explorer
```

Supply Chain 页面要求：

- Company / Product input。
- real/demo mode toggle。
- provider mode indicator。
- Sankey canvas。
- node drawer。
- edge drawer。
- evidence table。
- quality findings。
- fallback events。
- run status/progress。

### Sankey 交互

必须支持：

- 点击 node。
- 点击 edge。
- Expand from node。
- 合并 child graph。
- 标记 new nodes。
- 显示 edge value meaning。
- tooltip 明确：边宽不是采购金额，除非 `value_meaning == estimated_spend`。

### 涉及文件

```text
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/supply-chain-types.ts
frontend/src/components/SupplyChainExplorer.tsx
frontend/src/components/SupplyChainSankey.tsx
frontend/src/components/SupplyChainNodeDrawer.tsx
frontend/src/components/SupplyChainEvidencePanel.tsx
frontend/src/styles.css
frontend/src/components/SupplyChainExplorer.test.tsx
frontend/src/components/SupplyChainSankey.test.tsx
```

### 验收

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

手工验收：

```text
打开应用
→ 进入 Product Supply Chain tab
→ 输入 OpenAI / ChatGPT
→ Run
→ Sankey 出现
→ 点击 CPU
→ Drawer 显示 evidence
→ Expand
→ CPU 子图合并
```

## Phase 7：Observability、缓存、重试与成本控制

### 目标

真实工程化系统必须能回答：

- 搜索用了哪个 provider？
- 哪些 URL 被抓取？
- 哪一步 fallback 了？
- LLM 调用了几次？
- 每一步耗时多少？
- 为什么某条边是 needs_review？

### 新增字段

`SupplyChainTraceEvent` 增加：

```python
duration_ms: int | None
input_summary: dict
output_summary: dict
provider_calls: list[ProviderCall]
retry_count: int
cache_hit: bool
```

`ProviderCall`：

```python
class ProviderCall(BaseModel):
    provider: str
    operation: str
    status: Literal["success", "failed", "timeout", "cached"]
    latency_ms: int
    cost_estimate_usd: float | None
    error: str | None
```

### 策略

- Search timeout：10s。
- Web fetch timeout：15s。
- LLM timeout：60s。
- max provider calls per run。
- max LLM calls per run。
- cache TTL by source type。
- retry with exponential backoff。

### 涉及文件

```text
src/supply_chain/models.py
src/supply_chain/workflow.py
src/tools/search_cache.py
src/tools/search_router.py
src/config.py
tests/supply_chain/test_observability.py
```

### 验收

```bash
uv run pytest tests/supply_chain/test_observability.py -q
```

必须覆盖：

- trace 有 duration。
- provider failure 被记录。
- cache hit 被记录。
- retry_count 被记录。
- max provider calls 可阻断过度搜索。

## Phase 8：Production Test Matrix

### Unit Tests

```bash
uv run pytest tests/supply_chain -q
uv run pytest tests/graph -q
uv run pytest tests/api/test_supply_chain_api.py -q
```

### Core Regression

```bash
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api tests/reports tests/schemas -q
```

### Frontend

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

### Lint

核心目录：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api src/supply_chain src/graph
```

全仓目标：

```bash
uv run ruff check src tests
```

### Integration Tests

默认跳过，环境变量开启：

```bash
RUN_SEARCH_INTEGRATION=1 uv run pytest tests/supply_chain -m integration -q
RUN_NEO4J_INTEGRATION=1 uv run pytest tests/graph -m integration -q
RUN_LLM_INTEGRATION=1 uv run pytest tests/supply_chain -m llm -q
```

## Phase 9：Production Acceptance Cases

### Case A：OpenAI / ChatGPT

Mode：

```text
real search + cached fallback
```

必须输出：

```text
ChatGPT
→ cloud compute
→ GPU accelerator
→ CPU/server platform
→ HBM memory
→ networking
→ data center power
```

Confirmed suppliers 至少覆盖：

```text
Microsoft / Azure
NVIDIA
AMD or Intel
Broadcom or Arista
```

每条 confirmed edge 必须有 evidence。

### Case B：CPU recursive expansion

点击：

```text
component:cpu
```

必须输出：

```text
CPU
→ AMD / Intel
→ Foundry
→ TSMC / Intel Foundry
→ Lithography
→ ASML
→ EDA
→ Synopsys / Cadence
```

### Case C：Low evidence

输入一个冷门产品。

预期：

```text
workflow status = needs_review
evaluation.final_status = needs_review
confirmed edges 少
hypothesized edges 可见
warnings 可见
```

### Case D：Provider failure

模拟 search provider timeout。

预期：

```text
fallback event recorded
status != crash
cache used if available
quality warning visible
```

## 推荐执行顺序

```text
1. 修正 Evaluation final_status 语义
2. 接入前端主入口
3. 改 API 为后台任务
4. 实现 real SupplierDiscoveryStep
5. 实现 real RequirementDecomposerStep
6. 接入 Neo4j writer/query
7. 加 observability / retry / cache policy
8. 补 integration tests
9. 治理全仓 ruff
```

## 完成定义

当以下条件满足时，v18 才算真正工程化完成：

```text
Supply Chain Explorer 在主 UI 可访问。
POST /supply-chain/explore 不阻塞请求。
Real mode 能通过 SearchRouter 生成至少部分 evidence-backed edges。
LLM decomposer 有 schema validation 和 fallback。
Neo4j backend 可配置、可 mock test、可 integration test。
Sankey edge 全部可追溯 evidence 或明确 hypothesized。
Evaluation verdict 使用 pass / needs_review / fail。
Trace 可解释 provider calls、fallback、cache、latency。
OpenAI / ChatGPT 和 CPU expansion 两个案例在 real/cached 模式可重复运行。
核心 ruff、backend tests、frontend tests、build 全部通过。
```

## 与 `07-completion-summary.md` 的关系

`07-completion-summary.md` 表示：

```text
v18 demo acceptance completed
```

本文件表示：

```text
v18 production hardening is still required
```

后续完成本文件后，应新增：

```text
09-production-completion-summary.md
```

记录 production acceptance 的实际运行结果。
