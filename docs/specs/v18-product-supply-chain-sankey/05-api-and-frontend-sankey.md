# 05 - API 与 Frontend Sankey

## 目标

新增产品供应链探索 API 和前端 Sankey 视图，支持：

- 启动探索。
- 查询状态。
- 获取 Sankey payload。
- 点击节点递归展开。
- 查看 evidence 和 quality findings。

## Backend 新增文件

```text
src/api/supply_chain.py
tests/api/test_supply_chain_api.py
```

更新：

```text
src/api/main.py
```

## API 路由

### POST /supply-chain/explore

Request：

```json
{
  "company_name": "OpenAI",
  "product_name": "ChatGPT",
  "max_depth": 3,
  "max_suppliers_per_node": 5,
  "demo_mode": true
}
```

Response：

```json
{
  "run_id": "sc-run-...",
  "status": "queued",
  "sankey_url": "/supply-chain/sc-run-.../sankey"
}
```

### GET /supply-chain/{run_id}

Response：

```json
{
  "run_id": "sc-run-...",
  "status": "completed",
  "current_step": null,
  "node_count": 18,
  "link_count": 17,
  "evidence_count": 12,
  "evaluation": {
    "final_status": "pass"
  },
  "trace": []
}
```

### GET /supply-chain/{run_id}/sankey

Response：

```json
{
  "nodes": [],
  "links": [],
  "evidence": [],
  "warnings": []
}
```

### POST /supply-chain/expand

Request：

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

Response：

```json
{
  "run_id": "sc-run-child-...",
  "parent_run_id": "sc-run-...",
  "expanded_from_node_id": "component:cpu",
  "status": "queued",
  "sankey_url": "/supply-chain/sc-run-child-.../sankey"
}
```

## Run Store

可以复用 `InMemoryRunStore` 思路，但建议新增轻量 store：

```text
src/api/supply_chain.py
```

第一版可使用 in-memory dict。后续再迁移 SQLite / Redis。

要求：

- 测试可关闭 background。
- unknown run 返回 404。
- workflow exception 会记录 failed state。

## Frontend 新增文件

```text
frontend/src/supply-chain-types.ts
frontend/src/components/SupplyChainExplorer.tsx
frontend/src/components/SupplyChainSankey.tsx
frontend/src/components/SupplyChainEvidencePanel.tsx
frontend/src/components/SupplyChainNodeDrawer.tsx
frontend/src/components/SupplyChainExplorer.test.tsx
frontend/src/components/SupplyChainSankey.test.tsx
frontend/src/components/SupplyChainNodeDrawer.test.tsx
```

更新：

```text
frontend/src/api.ts
frontend/src/App.tsx
frontend/src/styles.css
frontend/package.json
```

## Sankey 库

推荐：

```bash
cd frontend && npm install @nivo/sankey
```

如果依赖过重，可使用：

```bash
cd frontend && npm install d3-sankey
```

第一版建议 `@nivo/sankey`，因为测试和 React 集成更快。

## 页面布局

```text
Supply Chain Explorer

左侧:
- Company
- Product
- Max depth
- Max suppliers per node
- Demo mode
- Run

中间:
- Sankey chart

右侧:
- Selected node / edge drawer
- Evidence
- Confidence
- Expand button

底部:
- Warnings
- Evaluation
```

## 交互要求

### Run

用户输入：

```text
OpenAI / ChatGPT
```

点击 Run：

```text
POST /supply-chain/explore
poll GET /supply-chain/{run_id}
GET /supply-chain/{run_id}/sankey
render Sankey
```

### Node Click

点击 `CPU`：

- 高亮相关边。
- 打开 drawer。
- 显示：
  - node type
  - confidence
  - suppliers
  - evidence
  - warnings
  - `Expand from this node`

### Expand

点击 `Expand from this node`：

```text
POST /supply-chain/expand
GET child sankey
merge child sankey into existing chart
```

Merge 规则：

- 相同 `node_id` 去重。
- 相同 `edge_id` 去重。
- 新节点使用视觉高亮。
- 保留 parent run 和 child run 的 evidence。

## UI 文案要求

不要把边宽说成金额，除非 `value_meaning == "estimated_spend"`。

建议显示：

```text
Flow width represents relative importance / confidence, not procurement spend.
```

但不要在页面上写长说明。可以放 tooltip。

## 测试要求

Backend：

```text
tests/api/test_supply_chain_api.py
```

测试：

- POST explore 返回 202。
- unknown run 返回 404。
- demo run 可同步完成。
- GET sankey 返回 nodes/links/evidence。
- POST expand 返回 child run。

Frontend：

```text
frontend/src/components/SupplyChainExplorer.test.tsx
frontend/src/components/SupplyChainSankey.test.tsx
frontend/src/components/SupplyChainNodeDrawer.test.tsx
```

测试：

- 表单默认值正确。
- 点击 Run 调用 API。
- Sankey 渲染节点 label。
- 点击 CPU 打开 drawer。
- 点击 Expand 调用 expand API。
- API error 显示错误状态。

验收命令：

```bash
uv run pytest tests/api/test_supply_chain_api.py -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

