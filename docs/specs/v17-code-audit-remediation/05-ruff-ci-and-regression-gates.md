# 05 - Ruff、CI 与 Regression Gates

## 目标

建立第 17 版局部质量门禁，先让新核心目录 ruff 归零，再逐步推广到全仓。

## 当前问题

审查时全仓：

```text
607 errors
```

新核心目录：

```text
src/workflows src/evaluation src/graph_reasoning src/reports src/api: 132 errors
```

目标不是一次性重构全仓，而是建立可执行、可维护的增量 gate。

## 第一阶段 Gate 范围

```text
src/workflows
src/evaluation
src/graph_reasoning
src/reports
src/api
```

命令：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
```

## 自动修复

先执行：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api --fix
```

然后手动处理不能自动修复的问题。

## 常见问题处理

### RUF006 asyncio.create_task

问题：

```text
create_task result 未保存，任务可能被 GC 或无法追踪
```

处理：

- 保存 task reference。
- 或使用 FastAPI `BackgroundTasks`。
- 或在 run store 中维护 task registry。

### E402 import not at top

处理：

- 移到文件顶部。
- 如为避免循环 import，使用局部 import 并添加必要注释，或重构到 schema re-export。

### F401 / F841 unused import / variable

处理：

- 删除未使用 import。
- 删除未使用变量。
- 如果用于 typing，放入 `if TYPE_CHECKING`。

### RUF022 __all__ not sorted

处理：

- 排序 `__all__`。

### E501 line too long

处理：

- 手动折行。
- 不为了折行牺牲可读性。

## 暂缓规则

复杂度类规则暂缓，不在第一阶段阻断：

```text
PLR0912
PLR0915
PLR0913
```

如当前配置已经启用，可在 plan 中明确 deferred，不要在功能修正中大规模重构。

## CI 建议

如果已有 GitHub Actions，增加：

```yaml
- name: Backend tests
  run: uv run pytest -q

- name: Core ruff gate
  run: uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api

- name: Frontend build
  working-directory: frontend
  run: |
    npm ci
    npm test -- --run
    npm run build
```

如果尚无 CI，可先创建文档和本地脚本，不强制引入 actions。

## Regression Gate

第 17 版每次修改后至少运行：

```bash
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

完成前运行：

```bash
uv run pytest -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 测试要求

新增或维护：

```text
tests/api/test_v16_payload_contract.py
tests/frontend_contract/test_graph_payload_fixture.py
```

如果 `tests/frontend_contract` 暂时不存在，可用 Python schema 检查前端 fixture JSON：

- `/graph` payload 字段完整。
- `/report` payload 字段完整。
- contract fixture 可 JSON round-trip。

验收命令：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
uv run pytest tests/api/test_v16_payload_contract.py -q
```

