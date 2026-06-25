# Step 18 - Product Supply Chain Explorer 与 Sankey 递归发现路线

## 目标

本文件是在 Step 15-17 的基础上新增的产品级供应链探索路线。现有项目已经具备：

- `SearchRouter` / browser exploration。
- 结构化 evidence / claim / entity schema。
- Neo4j graph writer / query。
- v16 graph reasoning subsystem。
- quality gate / guardrail engine。
- FastAPI workflow runtime。
- React 前端图谱展示。

第 18 版目标是把这些能力扩展为一个新的产品级能力：

```text
Product Supply Chain Explorer
```

中文定位：

> 输入一个公司和一个产品，自动发现该产品的主要上游产品、服务、基础设施、原材料和供应商公司，并用 Sankey 图展示供应链流向；用户点击任意上游节点后，可以以该节点作为新产品继续递归探索。

示例：

```text
Company: OpenAI
Product: ChatGPT
```

预期发现：

```text
ChatGPT
→ Cloud service
→ Microsoft Azure / Oracle / CoreWeave
→ GPU accelerator
→ NVIDIA / AMD
→ CPU
→ Intel / AMD
→ HBM memory
→ SK hynix / Samsung / Micron
→ Data center power
→ utilities / power producers
→ Networking
→ Broadcom / Arista / Cisco / Marvell
```

点击 `CPU` 后递归展开：

```text
CPU
→ AMD / Intel
→ Foundry
→ TSMC / Intel Foundry
→ Lithography
→ ASML
→ EDA
→ Synopsys / Cadence
→ Silicon wafer
→ Shin-Etsu / SUMCO
```

## 为什么作为新 Workflow

不要把该功能直接塞入当前 `FinRiskWorkflow`。原因：

- 当前 FinRisk workflow 的主语是“公司风险情报”。
- 新需求的主语是“产品供应链图谱”。
- 两者共享 evidence、search、graph、guardrail，但输入、输出和前端交互不同。

因此新增并行 workflow：

```text
SupplyChainExploreWorkflow
```

与现有系统关系：

```text
FinRisk Workflow
  → 公司风险、政策风险、地缘风险、投资研究问题

Product Supply Chain Explorer
  → 产品上游依赖、供应商、Sankey 可视化、递归探索

共享层
  → SearchRouter / Browser / LLM / Evidence / Neo4j / Guardrails / Frontend Shell
```

后续二者可以互相增强：

```text
产品供应链路径
→ 关键供应商
→ 进入 FinRisk workflow
→ 分析供应商风险、政策风险、地缘风险、潜在投资方向
```

## 新 Workflow 总览

```text
SupplyChainExploreRequest
   ↓
Product Resolver
   ↓
Requirement Decomposer
   ↓
Supplier Discovery
   ↓
Evidence Normalizer
   ↓
Supply Chain Graph Builder
   ↓
Sankey Payload Builder
   ↓
Quality Gate
   ↓
Frontend Sankey Explorer
```

点击节点递归展开：

```text
Sankey Node Click
   ↓
POST /supply-chain/expand
   ↓
New SupplyChainExploreRequest(parent_run_id, seed_node)
   ↓
Merge expanded subgraph into current Sankey payload
```

## 推荐目录结构

```text
src/
├── supply_chain/
│   ├── __init__.py
│   ├── models.py
│   ├── workflow.py
│   ├── prompts.py
│   ├── sankey.py
│   ├── fixtures.py
│   └── steps/
│       ├── __init__.py
│       ├── product_resolver.py
│       ├── requirement_decomposer.py
│       ├── supplier_discovery.py
│       ├── evidence_normalizer.py
│       ├── graph_builder.py
│       ├── sankey_builder.py
│       └── evaluator.py
├── api/
│   └── supply_chain.py
└── graph/
    └── supply_chain_queries.py

frontend/src/
├── components/
│   ├── SupplyChainExplorer.tsx
│   ├── SupplyChainSankey.tsx
│   ├── SupplyChainEvidencePanel.tsx
│   └── SupplyChainNodeDrawer.tsx
└── supply-chain-types.ts
```

测试目录：

```text
tests/
├── supply_chain/
│   ├── test_models.py
│   ├── test_workflow_demo.py
│   ├── test_requirement_decomposer.py
│   ├── test_supplier_discovery.py
│   ├── test_sankey_builder.py
│   ├── test_evaluator.py
│   └── fixtures/
│       └── openai_chatgpt_supply_chain.json
└── api/
    └── test_supply_chain_api.py

frontend/src/components/
├── SupplyChainExplorer.test.tsx
├── SupplyChainSankey.test.tsx
└── SupplyChainNodeDrawer.test.tsx
```

## 核心 Schema

新增 `src/supply_chain/models.py`。

核心 request：

```python
class SupplyChainExploreRequest(BaseModel):
    company_name: str | None = None
    ticker: str | None = None
    product_name: str
    max_depth: int = Field(default=3, ge=1, le=5)
    max_suppliers_per_node: int = Field(default=5, ge=1, le=10)
    focus_regions: list[str] = Field(default_factory=list)
    include_private_companies: bool = True
    demo_mode: bool = False
    cached_mode: bool = False
```

核心节点：

```python
class SupplyChainNode(BaseModel):
    node_id: str
    node_type: Literal[
        "company",
        "product",
        "component",
        "service",
        "commodity",
        "infrastructure",
        "energy",
        "region",
        "unknown",
    ]
    label: str
    normalized_name: str
    ticker: str | None = None
    depth: int = Field(ge=0)
    parent_node_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

核心边：

```python
class SupplyChainEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: Literal[
        "requires",
        "supplied_by",
        "depends_on",
        "manufactured_by",
        "hosted_on",
        "powered_by",
        "enabled_by",
        "hypothesized",
    ]
    value: float = Field(ge=0.0)
    value_meaning: Literal[
        "importance",
        "confidence_weight",
        "estimated_spend",
        "capacity_dependency",
    ] = "importance"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Sankey payload：

```python
class SankeyPayload(BaseModel):
    nodes: list[SupplyChainNode]
    links: list[SupplyChainEdge]
    evidence: list[NormalizedSupplyChainEvidence]
    warnings: list[str] = Field(default_factory=list)
```

## 数据来源策略

第一版分三层：

```text
Layer 1: Demo Fixture
Layer 2: SearchRouter + cached web evidence
Layer 3: Browser / SEC filing / transcript / Neo4j enrichment
```

### Demo Fixture

必须先保证 `OpenAI + ChatGPT` 离线演示稳定：

```text
tests/supply_chain/fixtures/openai_chatgpt_supply_chain.json
```

Fixture 要包含：

- product root。
- 一级上游需求。
- 供应商公司。
- evidence。
- Sankey payload。
- evaluator expected result。

### SearchRouter

复用现有 `src/tools/search_router.py`，新增 intent：

```text
product_supply_chain
supplier_discovery
component_supplier
cloud_dependency
datacenter_power
semiconductor_supply_chain
```

查询模板示例：

```text
{company} {product} supplier cloud provider evidence
{product} upstream components suppliers market share
{component} major suppliers companies official evidence
{company} {product} depends on {component}
```

### LLM 结构化抽取

LLM 可以用于：

- 把产品拆成上游需求。
- 从网页片段中抽取供应商关系。
- 生成自然语言解释。

LLM 不可以单独决定：

- Sankey edge 是否 confirmed。
- 供应商关系是否进入最终 confirmed graph。
- 边权重是否代表真实采购金额。

所有 confirmed edge 必须有 evidence。

## Neo4j 扩展

现有 `src/graph/schema.cypher` 已有 `Product`、`Supplier`、`Commodity`、`Evidence`，但需要补：

- `Component`
- `Service`
- `Infrastructure`
- `EnergySource`
- `DataCenter`

建议关系：

```text
(:Company)-[:OFFERS]->(:Product)
(:Product)-[:REQUIRES]->(:Component|Service|Infrastructure|Commodity)
(:Component)-[:SUPPLIED_BY]->(:Company)
(:Service)-[:HOSTED_ON]->(:Company)
(:Infrastructure)-[:POWERED_BY]->(:EnergySource|Company)
(:Company)-[:MANUFACTURES]->(:Component|Product)
(:Company)-[:DEPENDS_ON]->(:Company|Product|Component)
(:Claim)-[:SUPPORTED_BY]->(:Evidence)
```

关系属性：

```text
relation_id
confidence
evidence_ids
source
extraction_method
created_at
value
value_meaning
```

## 前端 Sankey 设计

新增视图：

```text
Supply Chain Explorer
```

布局：

```text
Left: launcher controls
Center: Sankey canvas
Right: selected node / edge details
Bottom: evidence table and quality findings
```

推荐库：

```text
@nivo/sankey
```

或：

```text
d3-sankey
```

第一版建议 `@nivo/sankey`，因为 React 集成更快，适合 demo。

交互：

- 点击 node：打开详情 drawer。
- 点击 edge：显示 evidence、confidence、source。
- 点击 `Expand from this node`：调用 `/supply-chain/expand`。
- 支持合并 expanded subgraph。
- 支持切换 edge width：
  - importance
  - confidence
  - estimated spend when available

## API 设计

新增：

```text
POST /supply-chain/explore
GET /supply-chain/{run_id}
GET /supply-chain/{run_id}/sankey
POST /supply-chain/expand
```

请求：

```json
{
  "company_name": "OpenAI",
  "product_name": "ChatGPT",
  "max_depth": 3,
  "max_suppliers_per_node": 5,
  "demo_mode": true
}
```

展开请求：

```json
{
  "parent_run_id": "sc-run-...",
  "node_id": "component:cpu",
  "product_name": "CPU",
  "seed_companies": ["Intel", "AMD"],
  "max_depth": 2,
  "demo_mode": true
}
```

## Quality Gate

新增 `SupplyChainEvaluator`，检查：

- 每个 confirmed edge 是否有 evidence。
- 每个 supplier company 是否有来源。
- 每个 URL 是否存在或在 cache 中。
- 是否把 hypothesis 当 confirmed。
- 是否存在没有 parent 的孤立节点。
- Sankey 是否存在 cycle。
- depth 是否超过 request.max_depth。
- confidence 是否在 0-1。
- edge value 是否非负。
- source diversity 是否达标。

输出：

```python
class SupplyChainEvaluation(BaseModel):
    schema_valid: bool
    graph_connected: bool
    acyclic_for_sankey: bool
    confirmed_edges_have_evidence: bool
    unsupported_edges: list[str]
    low_confidence_edges: list[str]
    source_diversity_score: float
    final_status: Literal["pass", "needs_review", "fail"]
```

## 分阶段实施

### Phase 1：Schema + Demo Fixture

目标：

- 新增 `src/supply_chain/models.py`。
- 新增 demo fixture。
- 新增 basic tests。

验收：

```bash
uv run pytest tests/supply_chain/test_models.py -q
```

### Phase 2：Workflow Skeleton

目标：

- 新增 `SupplyChainExploreWorkflow`。
- demo mode 从 fixture 生成完整 Sankey payload。

验收：

```bash
uv run pytest tests/supply_chain/test_workflow_demo.py -q
uv run python -m src.supply_chain.workflow --company OpenAI --product ChatGPT --demo-mode
```

### Phase 3：Search + Evidence

目标：

- 接入 SearchRouter。
- 新增供应链查询模板。
- 生成 evidence。

验收：

```bash
uv run pytest tests/supply_chain/test_supplier_discovery.py -q
```

### Phase 4：Graph Builder + Neo4j Query

目标：

- 写入产品供应链图。
- 支持从 Neo4j 或 fixture 读取路径。

验收：

```bash
uv run pytest tests/supply_chain/test_graph_builder.py -q
uv run pytest tests/graph/test_supply_chain_queries.py -q
```

### Phase 5：API

目标：

- 新增 `src/api/supply_chain.py`。
- 接入 `src/api/main.py`。

验收：

```bash
uv run pytest tests/api/test_supply_chain_api.py -q
```

### Phase 6：Frontend Sankey

目标：

- 新增 Sankey 页面。
- 点击节点递归展开。
- evidence drawer。

验收：

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

### Phase 7：Full Integration

验收：

```bash
uv run pytest tests/supply_chain tests/api -q
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

手工验收：

```text
OpenAI + ChatGPT
→ Sankey renders
→ Cloud / GPU / CPU / Power / Networking nodes visible
→ Click CPU
→ drawer opens
→ Expand from this node
→ CPU subgraph merges into Sankey
→ every confirmed edge has evidence
```

## 与正式投资研究目标的连接

该功能不是直接给买卖建议，而是生成研究方向：

```text
关键瓶颈供应商
关键二阶供应商
供应链集中度
政策/地缘暴露
潜在受益行业
需要进一步验证的问题
```

例如：

```text
ChatGPT demand growth
→ AI accelerator demand
→ NVIDIA / AMD
→ HBM demand
→ SK hynix / Samsung / Micron
→ advanced packaging / foundry
→ TSMC / ASE
```

最终输出应是：

```text
research_theme
supporting_evidence
confidence
limitations
next_research_questions
```

而不是：

```text
buy / sell / target price
```

## 详细 Specs

执行细节见：

```text
docs/specs/v18-product-supply-chain-sankey/00-index.md
docs/specs/v18-product-supply-chain-sankey/01-models-and-fixtures.md
docs/specs/v18-product-supply-chain-sankey/02-workflow-and-recursive-expansion.md
docs/specs/v18-product-supply-chain-sankey/03-search-extraction-and-evidence.md
docs/specs/v18-product-supply-chain-sankey/04-graph-storage-and-sankey-payload.md
docs/specs/v18-product-supply-chain-sankey/05-api-and-frontend-sankey.md
docs/specs/v18-product-supply-chain-sankey/06-testing-and-acceptance.md
```
