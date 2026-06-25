# 04 - Graph Storage 与 Sankey Payload

## 目标

把产品供应链探索结果写入图数据库或内存图，并生成前端可直接消费的 Sankey payload。

## 新增文件

```text
src/graph/supply_chain_queries.py
src/supply_chain/sankey.py
src/supply_chain/steps/graph_builder.py
src/supply_chain/steps/sankey_builder.py
tests/supply_chain/test_graph_builder.py
tests/supply_chain/test_sankey_builder.py
tests/graph/test_supply_chain_queries.py
```

## Neo4j Schema 扩展

更新：

```text
src/graph/schema.cypher
```

新增 constraints：

```cypher
CREATE CONSTRAINT component_entity_id IF NOT EXISTS
FOR (n:Component) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT service_entity_id IF NOT EXISTS
FOR (n:Service) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT infrastructure_entity_id IF NOT EXISTS
FOR (n:Infrastructure) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT energy_source_entity_id IF NOT EXISTS
FOR (n:EnergySource) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT datacenter_entity_id IF NOT EXISTS
FOR (n:DataCenter) REQUIRE n.entity_id IS UNIQUE;
```

推荐关系：

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

关系属性：

```text
relation_id
confidence
evidence_ids
source
extraction_method
value
value_meaning
created_at
```

## Graph Builder

`graph_builder.py` 职责：

- 将 `SupplyChainNode` 映射到 Neo4j label。
- 将 `SupplyChainEdge` 映射到关系。
- 对 `Evidence` 节点做 MERGE。
- 为 edge 和 evidence 建立支撑关系。

映射：

```text
node_type=company → Company
node_type=product → Product
node_type=component → Component
node_type=service → Service
node_type=commodity → Commodity
node_type=infrastructure → Infrastructure
node_type=energy → EnergySource
node_type=region → Region
```

写入要求：

- idempotent。
- Neo4j 不可用时返回 fallback event。
- demo mode 不连接 Neo4j。
- 不允许直接拼接未清洗 label 或 relation type。

## Supply Chain Queries

新增：

```python
def get_product_upstream_paths(
    client: Neo4jClient,
    product_node_id: str,
    depth: int = 3,
) -> list[SupplyChainPath]:
    ...
```

```python
def get_node_expansion_context(
    client: Neo4jClient,
    node_id: str,
    depth: int = 2,
) -> SupplyChainExpansionContext:
    ...
```

查询关系：

```cypher
MATCH p=(root {entity_id: $product_node_id})-[:REQUIRES|SUPPLIED_BY|MANUFACTURED_BY|HOSTED_ON|POWERED_BY|ENABLED_BY|DEPENDS_ON*1..$depth]->(n)
RETURN p
```

注意：

- Cypher 的 variable-length depth 不能直接用参数拼字符串之外的语法时，必须对 depth 做白名单。
- depth 只允许 1-5。

## Sankey Builder

输入：

```text
nodes: list[SupplyChainNode]
links: list[SupplyChainEdge]
evidence: list[NormalizedSupplyChainEvidence]
```

输出：

```text
SankeyPayload
```

必须处理：

- node 去重。
- link 去重。
- cycle detection。
- orphan node warnings。
- depth limit。
- edge sorting。
- low-confidence edge filtering option。

Cycle 处理：

```text
confirmed cycle → evaluator fail
hypothesized cycle → remove from sankey + warning
```

## Edge Value 策略

第一版默认：

```text
value_meaning = "importance"
value = normalized importance score, 0.1-1.0
```

计算建议：

```text
value = base_requirement_weight * confidence * source_quality
```

示例：

```text
ChatGPT → cloud compute: 1.0
cloud compute → GPU: 0.9
cloud compute → CPU: 0.55
cloud compute → networking: 0.45
cloud compute → power: 0.75
```

禁止：

- 没有采购额数据时将 value 命名为 revenue/spend。
- 在 UI 中暗示边宽就是真实金额。

## 测试要求

新增：

```text
tests/supply_chain/test_graph_builder.py
tests/supply_chain/test_sankey_builder.py
tests/graph/test_supply_chain_queries.py
```

测试用例：

- node_type 到 Neo4j label 映射正确。
- relation_type 到 Cypher 关系映射正确。
- 写入同一 node 两次 idempotent。
- depth 参数只允许 1-5。
- Sankey builder 去重重复 node。
- Sankey builder 拒绝 self-loop。
- Sankey builder 检测 cycle。
- orphan node 产生 warning。
- edge value 非负。
- confirmed edge 无 evidence 时 evaluator fail。

验收命令：

```bash
uv run pytest tests/supply_chain/test_graph_builder.py tests/supply_chain/test_sankey_builder.py tests/graph/test_supply_chain_queries.py -q
```

