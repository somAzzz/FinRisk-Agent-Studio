# Pydantic AI 迁移完成记录

## 结论

- 状态：完成
- 完成日期：2026-08-23
- 生产 Agent 运行时：Pydantic AI
- LLM 部署边界：外部 OpenAI-compatible 服务；本仓库不构建或启动 LLM 容器
- 回滚方式：部署迁移前版本；不再保留运行时 feature flag 或旧 tool loop

原计划中的 PAI-0 至 PAI-7 已全部落地。本文件现在是最终架构与验收记录，
不再作为 legacy/shadow 切换计划。

## 最终架构

Pydantic AI 负责：

- provider/model 构建与 OpenAI-compatible 接入；
- typed dependencies、structured output 和 toolset；
- Agent 消息协议、usage 与模型调用记录；
- 市场研究、Browser Explorer 页面摘要/动作选择、通用研究、申报风险提取和
  供应链结构化分析。

项目继续负责：

- evidence、claim、graph 和业务 schema；
- 工具权限、预算、审批与 SSRF/写入边界；
- run store、conversation、trace、quality gate 与 API contract；
- 模型不可用时的 cached/fixture/确定性业务降级。

业务降级不会调用另一套 LLM runtime。旧的 `AgentRuntime`、
`LLMToolAgentRuntime` 和自定义 OpenAI tool loop 已删除。

## Provider 合同

| Provider | Pydantic AI 接入 | Endpoint 来源 |
| --- | --- | --- |
| SGLang | `OpenAIChatModel` + `OpenAIProvider` | `SGLANG_BASE_URL` |
| vLLM | `OpenAIChatModel` + `OpenAIProvider` | `VLLM_BASE_URL` |
| OpenAI | 官方 provider | `OPENAI_BASE_URL` |
| DeepSeek | OpenAI-compatible provider | `DEEPSEEK_BASE_URL` |

每次运行通过 `LLMRunConfig` 和集中式 `src.ai.model_factory` 解析 provider、
模型、base URL 与凭据。业务模块不再读取环境变量来选择旧 runtime。

## 已完成的代码迁移

1. `src.ai.runtime_types` 成为工作流与 Pydantic AI adapter 的共享结果合同。
2. API、全局 Agent runtime 和通用研究 CLI 始终构建 Pydantic AI runtime。
3. Market Explorer 始终先运行 Pydantic AI；失败后只走确定性搜索降级。
   Browser Explorer 内部的页面摘要和下一步动作选择也已迁移为 typed Agent，
   不再直接调用 OpenAI-compatible SDK。
4. filing risk 与 supplier relation 使用 typed Pydantic AI output。
5. requirement decomposition、supplier proposal、node profile 的 JSON 边界通过
   Pydantic AI typed dict output，不再直接构建旧聊天 client。
6. `AGENT_RUNTIME_MODE` 已退役；旧环境值被忽略，不能恢复已删除代码。
7. 旧持久化记录的 `legacy`、`pydantic_ai_shadow`、
   `pydantic_ai_primary` 值仍可解析；新 run 统一写入 `pydantic_ai`。
8. API 的 `tool_loop_mode` 字段仅为旧客户端 wire compatibility 保留并忽略。
9. 以下实现及其专用测试已删除：
   - `src/agents/runtime.py`
   - `src/agents/llm_runtime.py`
   - `src/llm/client.py`
   - `src/llm/deepseek_client.py`
   - `src/llm/sglang_client.py`
   - `src/llm/tool_loop.py`
   - `src/tools/router.py`

`src/llm` 包和无生产调用方的独立 `ToolRouter` 已整体移除。仓库级回归测试会
扫描 `src/`，阻止这些模块、类、直接 `chat.completions` 调用和旧 tool-loop
方法重新出现。

## Docker 与部署边界

`docker-compose.yml` 只包含 Neo4j。SGLang/vLLM 由仓库外部的现有服务管理，
应用通过 `.env` 中的 provider endpoint、model 和 API key 连接它们。

```bash
docker compose up -d neo4j
docker compose config --services
# neo4j
```

外部服务的镜像、GPU、模型缓存、并行参数和生命周期不属于本项目 Compose。

## 验收证据

### 外部 SGLang live acceptance

2026-08-23 使用已运行的外部后端完成真实验收：

- endpoint：`http://127.0.0.1:30000/v1`
- model：`qwen3.8-27b`
- 结果：通过
- structured output：有效
- 本地工具调用：1
- provider requests：2
- input tokens：1075
- output tokens：183

同日另行执行 Browser Explorer live smoke：typed `PageSummary` 返回 188 个字符，
下一步返回经 `BrowserAction` 校验的 `search` 动作，结果通过。

验收命令：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --base-url http://127.0.0.1:30000/v1 \
  --model qwen3.8-27b
```

API key 仅从本地运行环境注入，不写入仓库或验收文档。

### 离线回归

迁移期间的定向回归覆盖配置、API、runtime adapter、structured clients、
Market Explorer、Supply Chain、通用研究 CLI、旧模块缺失与全模块导入。
最终验证为 `989 passed, 6 skipped`；frontend 为 18 个测试文件、76 项测试
通过，production build 通过。

## 运行与故障处理

1. 确认外部 endpoint 的 `/v1/models` 与 chat completions 可用。
2. 在 `.env` 配置 `LLM_PROVIDER`、对应 `*_BASE_URL`、`*_MODEL`、`*_API_KEY`。
3. 运行 live acceptance，再启动 API/worker。
4. provider 故障时，工作流按业务合同记录 fallback 并使用 cached/确定性路径；
   不切换到已删除的 LLM runtime。
5. 若 Pydantic AI 版本变更造成系统性回归，部署迁移前 Git tag，并保留失败
   run 的 trace 供比较。

## 后续维护约束

- 新增模型调用必须使用 Pydantic AI 和集中式 model factory。
- 新增 structured output 必须由 Pydantic model 验证。
- 不得在业务步骤中重新实现 OpenAI tool-call 循环。
- 本仓库不得新增 SGLang/vLLM Docker service；仅记录外部 endpoint 合同。
- provider 升级后必须重跑 offline tests、import gate 与至少一个 live acceptance。
