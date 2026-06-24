# Spec 03 - API Runtime 与 Workflow Run Storage

## 目标

为 FinRisk Agent Studio 提供最小 FastAPI 服务层，使前端和外部调用方可以启动 workflow、查询状态、读取报告。

## 范围

本 spec 负责：

- FastAPI app
- workflow run API
- in-memory run store
- basic background execution
- API tests

第一版不要求数据库持久化。后续可替换为 SQLite、Postgres 或 Redis。

## 新增文件

```text
src/api/__init__.py
src/api/main.py
src/api/workflows.py
src/api/run_store.py
tests/api/test_workflow_api.py
```

## API endpoints

### `POST /workflows/finrisk/run`

请求体：

```json
{
  "ticker": "AAPL",
  "analysis_goal": "Identify macro, policy and supply-chain risks that changed recently.",
  "time_horizon": "6-12 months",
  "year": 2024,
  "sources": ["filing", "web", "graph"],
  "max_browser_steps": 5,
  "demo_mode": true,
  "cached_mode": true
}
```

响应：

```json
{
  "run_id": "uuid",
  "status": "queued",
  "current_step": null,
  "started_at": "2026-06-24T10:00:00Z",
  "completed_at": null,
  "report_url": null
}
```

要求：

- 默认异步后台执行。
- `demo_mode=true` 时必须能在本地无外部依赖启动。
- 请求校验失败返回 422。

### `GET /workflows/{run_id}`

响应：

```json
{
  "run_id": "uuid",
  "status": "running",
  "current_step": "market_explorer",
  "trace": [],
  "company": {},
  "risk_count": 3,
  "evidence_count": 8,
  "completed_at": null
}
```

要求：

- 找不到 run 返回 404。
- 响应应足够支持前端 timeline。
- 不需要返回完整报告 markdown。

### `GET /workflows/{run_id}/report`

响应：

```json
{
  "run_id": "uuid",
  "status": "completed",
  "report": {},
  "markdown": "...",
  "evaluation": {}
}
```

要求：

- run 未完成时返回当前状态，可返回 409 或带 `status=running` 的 200，项目内保持一致即可。
- 找不到 run 返回 404。

## RunStore

第一版实现 `InMemoryRunStore`：

```python
class InMemoryRunStore:
    def create(self, request: FinRiskRequest) -> FinRiskWorkflowState: ...
    def get(self, run_id: str) -> FinRiskWorkflowState | None: ...
    def update(self, state: FinRiskWorkflowState) -> None: ...
    def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]: ...
```

要求：

- run_id 使用 UUID。
- 线程/异步安全：第一版可用 `asyncio.Lock` 或简单同步锁。
- 不将 API key 或敏感环境变量写入 state。

## Background execution

第一版可以使用 FastAPI `BackgroundTasks` 或 `asyncio.create_task`。

要求：

- workflow exception 要被捕获并写入 state。
- state.status 应更新为 `failed`。
- trace 中记录错误。

## API tests

新增 `tests/api/test_workflow_api.py`：

- `POST /workflows/finrisk/run` with demo mode returns run_id。
- `GET /workflows/{run_id}` returns status。
- `GET /workflows/{run_id}/report` eventually returns report for demo mode。
- unknown run returns 404。
- invalid request returns 422。

测试建议使用 FastAPI `TestClient`。

## 运行命令

```bash
uvicorn src.api.main:app --reload
```

## 验收命令

```bash
uv run pytest tests/api/test_workflow_api.py -q
uv run pytest tests/workflows -q
```

## 完成定义

- API 可以启动 demo workflow。
- API 可以查询 timeline 所需状态。
- API 可以返回 report 和 evaluation。
- 无需前端即可用 curl 完成一次 demo run。

