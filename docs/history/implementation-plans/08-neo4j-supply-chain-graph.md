# Step 08 - Neo4j 供应链图数据库

## 目标

把 Step 07 抽取到的实体、关系、claim 和 evidence 写入 Neo4j，并支持基础供应链图查询。

## 需要新增或修改的文件

新增：

```text
src/graph/__init__.py
src/graph/schema.cypher
src/graph/client.py
src/graph/writer.py
src/graph/queries.py
src/graph/algorithms.py
tests/graph/test_writer.py
tests/graph/test_queries.py
```

修改：

```text
docker-compose.yml
src/config.py
pyproject.toml
```

## 依赖

建议加入：

```text
neo4j
```

如果 `docker-compose.yml` 还没有 Neo4j 服务，需要补充：

```yaml
neo4j:
  image: neo4j:5
  ports:
    - "7474:7474"
    - "7687:7687"
  environment:
    - NEO4J_AUTH=neo4j/password
```

## 图模型

节点：

```text
Company
Product
Segment
Customer
Supplier
Competitor
Region
Country
Commodity
Policy
Risk
Opportunity
Filing
Transcript
Article
Event
Executive
Claim
Evidence
```

关系：

```text
SUPPLIES_TO
BUYS_FROM
CUSTOMER_OF
COMPETES_WITH
HAS_SEGMENT
SELLS_PRODUCT
DEPENDS_ON
EXPOSED_TO
MENTIONS_RISK
IMPACTED_BY
BENEFITS_FROM
SUBSIDIARY_OF
SUPPORTED_BY
```

## schema.cypher

应包含 constraints：

```cypher
CREATE CONSTRAINT company_entity_id IF NOT EXISTS
FOR (n:Company) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT evidence_id IF NOT EXISTS
FOR (n:Evidence) REQUIRE n.evidence_id IS UNIQUE;

CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (n:Claim) REQUIRE n.claim_id IS UNIQUE;
```

其它实体也应有 `entity_id` unique constraint。

## Graph Client

```python
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        ...

    def run(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        ...

    def close(self) -> None:
        ...
```

要求：

- 支持 context manager。
- 测试中可替换为 fake client。

## Graph Writer

```python
class GraphWriter:
    def write_entity(self, entity: Entity) -> None:
        ...

    def write_evidence(self, evidence: Evidence) -> None:
        ...

    def write_relation(self, relation: Relation) -> None:
        ...

    def write_claim(self, claim: Claim) -> None:
        ...

    def write_extraction_result(self, result: ExtractionResult) -> None:
        ...
```

写入规则：

- 使用 `MERGE` 防止重复。
- Entity label 根据 `entity_type` 映射。
- Evidence 单独作为节点。
- Relation 写入真实实体边，同时把 evidence 连接到边对应 claim。
- Neo4j 不支持关系再连关系，因此建议：
  - 实体之间写业务关系。
  - 另建 Claim 节点表示这条关系的证据说明。
  - `Claim -[:SUPPORTED_BY]-> Evidence`。

## Graph Queries

基础查询：

```python
def get_upstream_suppliers(ticker: str, depth: int = 2) -> list[GraphPath]:
    ...

def get_downstream_customers(ticker: str, depth: int = 2) -> list[GraphPath]:
    ...

def get_policy_beneficiaries(policy_name: str) -> list[CompanyExposure]:
    ...

def get_geopolitical_exposures(region: str) -> list[CompanyExposure]:
    ...

def get_claim_evidence(claim_id: str) -> list[Evidence]:
    ...
```

## Graph Algorithms

初版可以只封装 Cypher 查询，不必须安装 GDS。

建议：

- degree centrality：找供应链中心节点。
- path search：找公司之间供应链路径。
- community detection 和 link prediction 留 TODO。

## 测试策略

单元测试用 fake Neo4j client，检查生成的 Cypher 和参数。

可选集成测试：

```bash
RUN_NEO4J_INTEGRATION=1 pytest tests/graph -m integration
```

测试覆盖：

- entity MERGE。
- evidence MERGE。
- claim 写入。
- relation 写入。
- extraction result 批量写入。
- query 函数返回结构化结果。

## 验收标准

- 可以把 Step 07 的抽取结果写入 Neo4j。
- 可以查询某 ticker 的上游和下游。
- 每个 claim 可追溯 evidence。
- 没有 Neo4j 运行时，单元测试仍可通过。

## 给执行助手的注意事项

- 不要把所有属性都塞成 JSON 字符串，常用字段应是 Neo4j 属性。
- 注意 label 和 relationship type 的合法字符。
- 对 confidence、source_type、filing_year 建索引可留后续优化。

