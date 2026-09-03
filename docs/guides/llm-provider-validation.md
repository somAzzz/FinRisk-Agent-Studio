# LLM Provider 配置与验收

FinRisk 只使用 Pydantic AI 作为模型调用和 Agent 运行时。SGLang、vLLM、DeepSeek 与 OpenAI 通过集中式 model factory 接入；仓库不启动或管理 LLM 服务。

## 配置

复制示例配置：

```bash
cp .env.example .env
```

设置 `LLM_PROVIDER`，并填写对应的 `*_BASE_URL`、`*_MODEL` 和 `*_API_KEY`。不要把真实凭据写入命令、artifact、日志或 Git。

本地 Compose 只负责可选的 Neo4j：

```bash
docker compose up -d neo4j
docker compose config --services
```

## 最小 live 验收

以下命令会验证一次真实 structured output、本地 typed tool call 和 usage 记录，不发送项目或用户数据：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --base-url http://127.0.0.1:30000/v1 \
  --model qwen3.8-27b
```

将 `--provider` 换成 `vllm`、`deepseek` 或 `openai` 即可验证其他后端。凭据只从当前环境读取。

## 发布前检查

```bash
uv lock --check
uv run pytest -m "not integration" -q
uv run ruff check src tests scripts
docker compose config --services
```

业务级真实数据验收另见 [真实数据验收](../testing/real-data-acceptance.md)。

## 故障语义

- endpoint 或 model 配置错误：配置阶段或请求阶段明确失败，不静默切换 provider。
- 单次 provider 故障：业务工作流按自身合同降级到 cached、fixture 或确定性路径，并在 trace 中记录原因。
- Pydantic AI 系统性回归：回滚部署 revision；项目不保留第二套 legacy runtime。
- live 验收失败：不能用 demo 通过替代，应保留脱敏后的错误类型、模型名和 endpoint 合同用于定位。
