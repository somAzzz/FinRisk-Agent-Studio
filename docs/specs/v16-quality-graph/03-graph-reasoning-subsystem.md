# V16 Spec 03 - Graph Reasoning 子系统

## 目标

把 Graph Reasoner 从单一 workflow step 升级为完整子系统：

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ LLM/Template Path Interpreter
→ Graph Insight Validator
```

## 新增目录

```text
src/graph_reasoning/
├── __init__.py
├── models.py
├── context_builder.py
├── path_retriever.py
├── path_scorer.py
├── evidence_binder.py
├── path_interpreter.py
├── insight_validator.py
└── fixture_graph.py
tests/graph_reasoning/
├── test_context_builder.py
├── test_path_retriever.py
├── test_path_scorer.py
├── test_insight_validator.py
└── test_graph_reasoner_step.py
```

## Graph models

`src/graph_reasoning/models.py`：

```python
class GraphNode(BaseModel):
    node_id: str
    node_type: Literal[
        "Company",
        "Ticker",
        "Filing",
        "Risk",
        "Evidence",
        "Claim",
        "Supplier",
        "Sector",
        "Region",
        "Policy",
        "MacroFactor",
        "Event",
        "Opportunity",
    ]
    label: str
    properties: dict[str, Any] = {}


class GraphEdgeMetadata(BaseModel):
    source: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    extraction_method: Literal["rule", "llm", "manual", "imported"]
    created_at: datetime


class GraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    metadata: GraphEdgeMetadata


class GraphQueryContext(BaseModel):
    company_id: str
    ticker: str
    risk_ids: list[str]
    focus_entities: list[str]
    focus_risk_types: list[str]
    max_hops: int = Field(default=3, ge=1, le=4)
    allowed_edge_types: list[str]


class CandidateGraphPath(BaseModel):
    path_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    path_text: str
    evidence_ids: list[str]
    hop_count: int
    path_score: float | None = None
    score_breakdown: dict[str, float] = {}
```

## Graph Context Builder

输入：

- company
- filing risks
- normalized evidence
- claims
- analysis goal

输出：

- `GraphQueryContext`

规则：

- supply_chain risk -> allowed edges include supplier/region/risk edges。
- policy risk -> allowed edges include policy/sector/company/risk edges。
- geopolitical risk -> allowed edges include region/risk/supplier/company edges。
- max_hops 默认 3，MVP 不超过 4。

## Candidate Path Retriever

第一版支持两种 backend：

```text
fixture
neo4j
```

fixture backend 必须离线可运行。

Neo4j 查询示例：

```cypher
MATCH path = (c:Company {ticker: $ticker})-[*1..3]-(n)
WHERE ALL(r IN relationships(path)
          WHERE coalesce(r.confidence, 0.0) >= 0.5)
RETURN path
LIMIT 50
```

要求：

- 不让 LLM 编路径。
- 所有路径必须由 backend 返回。
- path nodes 和 edges 必须结构化。

## Evidence Binder

职责：

- 将 path edge metadata 中的 evidence_ids 对应到 state.normalized_evidence。
- 若 edge 无 evidence，则标记 hypothesis edge。

规则：

- final insight 必须至少有一个 evidence-backed path。
- 无 evidence edge 的路径可以保留，但 guardrail status 为 warning/needs_review。

## Path Scorer

公式：

```text
path_score =
  0.25 * evidence_coverage
  + 0.20 * min_edge_confidence
  + 0.20 * relevance_to_analysis_goal
  + 0.15 * source_quality
  + 0.10 * novelty
  + 0.10 * graph_centrality
  - 0.05 * hub_penalty
```

指标：

- `evidence_coverage`: 有 evidence 的 edge 占比。
- `min_edge_confidence`: 路径最弱边。
- `relevance_to_analysis_goal`: keyword overlap v1。
- `source_quality`: 关联 evidence 的平均 source quality。
- `novelty`: 是否提供 filing 之外的新信息。
- `graph_centrality`: MVP 可用简单 degree proxy。
- `hub_penalty`: generic node 惩罚。

要求：

- `path_score` clamp 到 0-1。
- score_breakdown 必须保存。
- LLM 不直接修改 path_score。

## Path Interpreter

第一版支持：

```text
template interpreter
optional LLM interpreter
```

LLM 输入只包含 top ranked paths，不包含全图。

输出：

```python
class GraphInsight(BaseModel):
    insight_id: str
    source_company: str
    insight_type: Literal[
        "second_order_risk",
        "supply_chain_exposure",
        "policy_transmission",
        "market_opportunity",
        "research_hypothesis",
    ]
    risk_path_ids: list[str]
    affected_entities: list[str]
    explanation: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    uncertainty: str
    recommended_next_questions: list[str]
    research_theme: str | None = None
```

要求：

- 不使用 `investment_theme`。
- market opportunity 必须写成 research theme / hypothesis。
- recommended questions 不能是 buy/sell action。

## Insight Validator

检查：

- insight path_id exists。
- affected_entities belong to path nodes。
- evidence_ids exist。
- confidence <= max(path_score) + 0.1。
- path length 2-4 hops。
- edge evidence present or hypothesis marked。
- no fabricated node。

输出：

- GuardrailFinding list。
- 可修改 insight confidence，降低过高 confidence。

## Graph JSON 输出

为前端生成：

```python
class EvidenceGraphPayload(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    paths: list[CandidateGraphPath]
    insights: list[GraphInsight]
    guardrail_findings: list[GuardrailFinding]
```

## 验收测试

测试点：

- fixture graph can return candidate paths。
- path score in 0-1。
- path with missing evidence gets warning。
- insight referencing missing path fails。
- confidence too high gets downgraded。
- no fabricated affected entity allowed。
- graph reasoner step writes graph_paths and graph_insights to state。

## 验收命令

```bash
uv run pytest tests/graph_reasoning -q
```

