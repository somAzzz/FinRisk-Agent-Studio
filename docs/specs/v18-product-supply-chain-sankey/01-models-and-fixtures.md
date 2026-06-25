# 01 - Models 与 Demo Fixtures

## 目标

新增产品供应链探索的 Pydantic schema，并提供稳定 demo fixture，保证后续 workflow、API、前端和测试都有确定输入输出。

## 新增文件

```text
src/supply_chain/__init__.py
src/supply_chain/models.py
src/supply_chain/fixtures.py
tests/supply_chain/fixtures/openai_chatgpt_supply_chain.json
tests/supply_chain/test_models.py
```

## 必须实现的 Models

### SupplyChainExploreRequest

字段：

```python
company_name: str | None
ticker: str | None
product_name: str
max_depth: int = Field(default=3, ge=1, le=5)
max_suppliers_per_node: int = Field(default=5, ge=1, le=10)
focus_regions: list[str] = []
include_private_companies: bool = True
demo_mode: bool = False
cached_mode: bool = False
```

验证规则：

- `product_name` 不能为空。
- `company_name` 和 `ticker` 至少一个有值，除非 `parent_run_id` expansion 场景提供 `seed_node_id`。
- `max_depth` 不得超过 5。

### SupplyChainNode

字段：

```python
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
ticker: str | None
depth: int
parent_node_id: str | None
confidence: float
evidence_ids: list[str]
metadata: dict[str, Any]
```

要求：

- `node_id` 用稳定 ID，不使用随机 UUID 作为唯一来源。
- 建议格式：

```text
company:openai
product:chatgpt
component:gpu-accelerator
service:cloud-compute
company:nvidia
```

### SupplyChainEdge

字段：

```python
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
value: float
value_meaning: Literal[
    "importance",
    "confidence_weight",
    "estimated_spend",
    "capacity_dependency",
]
confidence: float
evidence_ids: list[str]
metadata: dict[str, Any]
```

要求：

- `value >= 0`。
- `confidence` 在 0-1。
- confirmed relation 必须有 `evidence_ids`。
- `hypothesized` 可以没有 evidence，但必须在 metadata 里说明 reason。

### NormalizedSupplyChainEvidence

建议字段：

```python
evidence_id: str
source_type: Literal["web", "filing", "transcript", "company", "manual", "fixture"]
source_name: str | None
url: str | None
title: str | None
quote: str
summary: str
retrieved_at: datetime
published_at: datetime | None
confidence: float
metadata: dict[str, Any]
```

### SankeyPayload

字段：

```python
nodes: list[SupplyChainNode]
links: list[SupplyChainEdge]
evidence: list[NormalizedSupplyChainEvidence]
warnings: list[str]
```

验证规则：

- 所有 `links.source_node_id` 和 `links.target_node_id` 必须存在于 nodes。
- Sankey links 不允许自环。
- 第一版不允许 cycle。

### SupplyChainExploreState

字段：

```python
run_id: str
request: SupplyChainExploreRequest
status: Literal["queued", "running", "completed", "failed", "needs_review"]
nodes: list[SupplyChainNode]
links: list[SupplyChainEdge]
evidence: list[NormalizedSupplyChainEvidence]
sankey: SankeyPayload | None
evaluation: SupplyChainEvaluation | None
trace: list[SupplyChainTraceEvent]
parent_run_id: str | None
expanded_from_node_id: str | None
```

## Demo Fixture 要求

文件：

```text
tests/supply_chain/fixtures/openai_chatgpt_supply_chain.json
```

必须包含：

- `request`
- `nodes`
- `links`
- `evidence`
- `sankey`
- `expected_expansions`

最低节点：

```text
company:openai
product:chatgpt
service:cloud-compute
company:microsoft
company:oracle
company:coreweave
component:gpu-accelerator
company:nvidia
component:cpu
company:amd
company:intel
component:hbm-memory
company:sk-hynix
company:samsung
company:micron
component:networking
company:broadcom
company:arista
energy:datacenter-power
```

最低边：

```text
product:chatgpt -> service:cloud-compute
service:cloud-compute -> company:microsoft
service:cloud-compute -> company:oracle
service:cloud-compute -> company:coreweave
service:cloud-compute -> component:gpu-accelerator
component:gpu-accelerator -> company:nvidia
service:cloud-compute -> component:cpu
component:cpu -> company:amd
component:cpu -> company:intel
component:gpu-accelerator -> component:hbm-memory
component:hbm-memory -> company:sk-hynix
component:hbm-memory -> company:samsung
component:hbm-memory -> company:micron
service:cloud-compute -> component:networking
component:networking -> company:broadcom
component:networking -> company:arista
service:cloud-compute -> energy:datacenter-power
```

## 测试要求

新增：

```text
tests/supply_chain/test_models.py
```

测试用例：

- `SupplyChainExploreRequest` 校验空产品名失败。
- `max_depth > 5` 失败。
- `confidence > 1` 失败。
- link 指向不存在 node 时 `SankeyPayload` 校验失败。
- self-loop link 校验失败。
- confirmed edge 无 evidence 时 evaluator 后续应标记 fail。
- fixture 可以被完整加载并通过 schema validate。

验收命令：

```bash
uv run pytest tests/supply_chain/test_models.py -q
```

