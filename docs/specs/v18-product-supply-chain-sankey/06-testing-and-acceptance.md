# 06 - Testing 与完整验收

## 目标

定义第 18 版功能的完整测试矩阵和验收标准，保证该功能不是只有文档和 UI，而是能用自动化测试证明：

- schema 正确。
- workflow 可运行。
- evidence 可追溯。
- Sankey payload 合法。
- API 可用。
- 前端可交互。
- 递归展开可验证。

## 测试目录

新增：

```text
tests/supply_chain/
├── fixtures/
│   └── openai_chatgpt_supply_chain.json
├── test_models.py
├── test_workflow_demo.py
├── test_recursive_expansion.py
├── test_requirement_decomposer.py
├── test_supplier_discovery.py
├── test_evidence_normalizer.py
├── test_graph_builder.py
├── test_sankey_builder.py
└── test_evaluator.py

tests/api/
└── test_supply_chain_api.py

tests/graph/
└── test_supply_chain_queries.py

frontend/src/components/
├── SupplyChainExplorer.test.tsx
├── SupplyChainSankey.test.tsx
└── SupplyChainNodeDrawer.test.tsx
```

## Backend 单元测试

### Models

命令：

```bash
uv run pytest tests/supply_chain/test_models.py -q
```

必须覆盖：

- request validation。
- node validation。
- edge validation。
- sankey reference validation。
- fixture validation。

### Workflow Demo

命令：

```bash
uv run pytest tests/supply_chain/test_workflow_demo.py -q
```

必须覆盖：

- `OpenAI + ChatGPT` demo workflow completed。
- node_count > 0。
- link_count > 0。
- evidence_count > 0。
- root product 是 `product:chatgpt`。
- 包含 `component:cpu`、`component:gpu-accelerator`、`energy:datacenter-power`。

### Recursive Expansion

命令：

```bash
uv run pytest tests/supply_chain/test_recursive_expansion.py -q
```

必须覆盖：

- 以 `component:cpu` 展开。
- child run 记录 `parent_run_id`。
- child run 记录 `expanded_from_node_id`。
- CPU 子图包含 `company:amd`、`company:intel`。
- CPU 子图包含 `company:tsmc` 或 `company:asml`。
- parent state 不被 child workflow 修改。

### Supplier Discovery

命令：

```bash
uv run pytest tests/supply_chain/test_supplier_discovery.py -q
```

必须覆盖：

- mock search provider 结果可生成 supplier relation。
- source URL 为空时不 confirmed。
- quote 为空时不 confirmed。
- confidence 低于阈值时进入 hypothesized。
- SearchRouter failure 使用 fallback。

### Sankey Builder

命令：

```bash
uv run pytest tests/supply_chain/test_sankey_builder.py -q
```

必须覆盖：

- duplicate node 去重。
- duplicate edge 去重。
- self-loop fail。
- cycle fail 或 warning + remove。
- orphan node warning。
- edge value 非负。
- edge value_meaning 合法。

### Evaluator

命令：

```bash
uv run pytest tests/supply_chain/test_evaluator.py -q
```

必须覆盖：

- confirmed edge 无 evidence → fail。
- hypothesized edge 无 evidence → needs_review。
- low source diversity → needs_review。
- valid fixture → pass。
- max_depth overflow → fail。
- disconnected graph → needs_review 或 fail。

## API 测试

命令：

```bash
uv run pytest tests/api/test_supply_chain_api.py -q
```

必须覆盖：

- `POST /supply-chain/explore`。
- `GET /supply-chain/{run_id}`。
- `GET /supply-chain/{run_id}/sankey`。
- `POST /supply-chain/expand`。
- unknown run 404。
- failed workflow 返回 failed state。

## Graph 测试

命令：

```bash
uv run pytest tests/graph/test_supply_chain_queries.py -q
```

必须覆盖：

- depth 白名单。
- query 参数正确传递。
- path record 转 model。
- Neo4j unavailable 时上层 graph_builder fallback。

## Frontend 测试

命令：

```bash
cd frontend && npm test -- --run
```

必须覆盖：

- SupplyChainExplorer 表单可填写。
- Run 按钮调用 API。
- loading 状态可见。
- Sankey 节点渲染。
- 点击 CPU 打开 drawer。
- drawer 显示 evidence。
- Expand 调用 `/supply-chain/expand`。
- child Sankey merge 后新节点可见。
- API error 显示错误状态。

构建验收：

```bash
cd frontend && npm run build
```

## 全量回归

第 18 版完成前必须跑：

```bash
uv run pytest tests/supply_chain tests/api tests/graph -q
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

如果 `tests/graph` 原本不存在，实现时创建。

## 手工验收脚本

### Case 1：OpenAI / ChatGPT

输入：

```text
Company: OpenAI
Product: ChatGPT
Demo mode: on
Depth: 3
```

预期：

- Sankey 成功渲染。
- 可见 `Cloud service`。
- 可见 `GPU accelerator`。
- 可见 `CPU`。
- 可见 `Data center power`。
- 可见 `NVIDIA`。
- 可见 `AMD` / `Intel`。
- 每条 confirmed edge 有 evidence。

### Case 2：点击 CPU 展开

操作：

```text
Click CPU
Click Expand from this node
```

预期：

- drawer 显示 CPU。
- child run 完成。
- Sankey 合并 CPU 子图。
- 可见 `TSMC` 或 `Intel Foundry`。
- 可见 `ASML`。
- 新增边有 confidence 和 evidence / warning。

### Case 3：Quality Gate

操作：

使用一条无 evidence 的 confirmed edge fixture。

预期：

```text
final_status = fail 或 needs_review
unsupported_edges 非空
前端显示 warning
```

## 完成定义

第 18 版完成需要满足：

- 有总 plan。
- 有 specs。
- 有 schema。
- 有 demo fixture。
- 有 workflow。
- 有 API。
- 有 frontend Sankey。
- 有 recursive expansion。
- 有 evaluator。
- 有 backend tests。
- 有 frontend tests。
- 全量回归通过。

最终用户体验：

```text
OpenAI + ChatGPT
→ Run
→ Sankey graph
→ Click CPU
→ Evidence drawer
→ Expand
→ CPU upstream Sankey subgraph
```

最终工程质量：

```text
No confirmed edge without evidence.
No Sankey cycle.
No fake spend value.
No direct investment advice.
All demo flows pass tests.
```
