# 02 - Workflow 与递归展开

## 目标

新增 `SupplyChainExploreWorkflow`，支持：

- 初始探索：`Company + Product`。
- 节点递归展开：点击 Sankey 节点后以该节点作为新产品继续探索。
- demo mode 离线运行。
- cached fallback。
- step trace 和 quality gate。

## 新增文件

```text
src/supply_chain/workflow.py
src/supply_chain/steps/__init__.py
src/supply_chain/steps/product_resolver.py
src/supply_chain/steps/requirement_decomposer.py
src/supply_chain/steps/supplier_discovery.py
src/supply_chain/steps/evidence_normalizer.py
src/supply_chain/steps/graph_builder.py
src/supply_chain/steps/sankey_builder.py
src/supply_chain/steps/evaluator.py
tests/supply_chain/test_workflow_demo.py
tests/supply_chain/test_recursive_expansion.py
```

## Workflow 顺序

```text
Product Resolver
→ Requirement Decomposer
→ Supplier Discovery
→ Evidence Normalizer
→ Supply Chain Graph Builder
→ Sankey Payload Builder
→ Supply Chain Evaluator
```

## CLI 入口

实现：

```bash
uv run python -m src.supply_chain.workflow \
  --company OpenAI \
  --product ChatGPT \
  --max-depth 3 \
  --demo-mode
```

输出必须包含：

- run_id
- status
- node_count
- link_count
- evidence_count
- evaluation.final_status
- sankey JSON path 或 stdout 摘要

## Product Resolver

职责：

- 标准化公司和产品。
- 生成 root company / root product node。
- 对 OpenAI 这类非上市公司允许 `ticker=None`。

输入：

```json
{
  "company_name": "OpenAI",
  "product_name": "ChatGPT"
}
```

输出：

```text
company:openai
product:chatgpt
```

## Requirement Decomposer

职责：

- 把产品拆成主要上游需求。
- demo mode 从 fixture 读取。
- real mode 使用 LLM structured output + rule fallback。

ChatGPT 第一层要求至少包含：

```text
cloud compute
GPU accelerator
CPU
HBM memory
networking
data center power
```

输出关系：

```text
product:chatgpt -requires-> service:cloud-compute
service:cloud-compute -requires-> component:gpu-accelerator
service:cloud-compute -requires-> component:cpu
service:cloud-compute -requires-> energy:datacenter-power
```

## Supplier Discovery

职责：

- 对每个 requirement 找供应商公司。
- demo mode 从 fixture 读取。
- real mode 调 SearchRouter。

搜索意图：

```text
product_supply_chain
supplier_discovery
component_supplier
cloud_dependency
datacenter_power
semiconductor_supply_chain
```

输出：

```text
component:gpu-accelerator -supplied_by-> company:nvidia
component:cpu -supplied_by-> company:amd
component:cpu -supplied_by-> company:intel
```

## Evidence Normalizer

职责：

- 将 fixture/search/browser/filing evidence 统一成 `NormalizedSupplyChainEvidence`。
- 将 edge.evidence_ids 映射到 evidence table。
- 去重 URL 和重复 quote。

## Graph Builder

职责：

- 将 nodes / links 写入 Neo4j 或内存图。
- demo mode 不要求 Neo4j。
- real mode 可 best-effort 写入，失败不阻断 Sankey 输出，但记录 fallback event。

## Sankey Builder

职责：

- 从 nodes / links 生成 acyclic Sankey payload。
- 过滤不适合 Sankey 的 cycle。
- 保留 warnings。

## Evaluator

职责：

- 校验 schema。
- 校验 evidence coverage。
- 校验 graph connected。
- 校验 Sankey acyclic。
- 校验 depth。
- 校验 source diversity。

## 递归展开

新增 expansion request：

```python
class SupplyChainExpandRequest(BaseModel):
    parent_run_id: str
    node_id: str
    product_name: str | None = None
    seed_companies: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_suppliers_per_node: int = Field(default=5, ge=1, le=10)
    demo_mode: bool = False
    cached_mode: bool = False
```

行为：

1. 从 parent run 读取已选 node。
2. 将该 node 转换为新的 root product/component。
3. 运行同一 workflow。
4. 将子图返回给前端。
5. 前端负责 merge，也可以由 API 返回 merged payload。

CPU demo expansion 必须返回：

```text
component:cpu
→ company:amd
→ company:intel
→ service:foundry
→ company:tsmc
→ company:intel-foundry
→ component:lithography
→ company:asml
→ service:eda
→ company:synopsys
→ company:cadence
```

## 测试要求

新增：

```text
tests/supply_chain/test_workflow_demo.py
tests/supply_chain/test_recursive_expansion.py
```

测试用例：

- demo workflow 对 `OpenAI + ChatGPT` 完成并返回 `completed`。
- demo workflow 产生非空 nodes / links / evidence。
- root node 是 `product:chatgpt`。
- Sankey payload 包含 `component:cpu`。
- 点击 `component:cpu` 的 expansion 返回 CPU 子图。
- expansion 的 `parent_run_id` 被保留。
- expansion 不污染 parent state。
- max_depth 被严格限制。

验收命令：

```bash
uv run pytest tests/supply_chain/test_workflow_demo.py tests/supply_chain/test_recursive_expansion.py -q
uv run python -m src.supply_chain.workflow --company OpenAI --product ChatGPT --demo-mode
```

