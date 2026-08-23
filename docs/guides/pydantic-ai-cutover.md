# Pydantic AI 运行手册

迁移已经完成。当前没有 legacy/shadow/primary 切换步骤；Pydantic AI 是唯一
Agent runtime。

## 配置外部后端

```bash
cp .env.example .env
```

设置 `LLM_PROVIDER`，并填写对应的 `*_BASE_URL`、`*_MODEL` 和 `*_API_KEY`。
本项目不会启动 LLM Docker 容器。

## 启动项目依赖

```bash
docker compose up -d neo4j
docker compose config --services
```

服务列表应只有 `neo4j`。

## Live acceptance

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --base-url http://127.0.0.1:30000/v1 \
  --model qwen3.8-27b
```

不要把 API key 写入命令历史、artifact 或仓库；从本地环境注入。

## 发布前检查

```bash
uv lock --check
uv run pytest -m "not integration" -q
uv run ruff check src tests scripts
docker compose config --services
```

同时确认源码回归测试通过，且不存在旧 runtime 文件或自定义 tool-loop 引用。

## 故障处理

- 单次 provider 错误：检查 run trace 和 fallback event；业务工作流会按合同降级。
- endpoint/model 配置错误：修正 `.env` 后重跑 live acceptance。
- Pydantic AI 系统性回归：部署迁移前版本；不设置 `AGENT_RUNTIME_MODE=legacy`，
  因为该变量已退役且旧实现已删除。
