# Pydantic AI 迁移完成记录

> 归档说明：本文记录已经完成的运行时迁移及当时的验收基线，不再作为当前实施计划或运维入口。当前架构以 `docs/ARCHITECTURE.md` 和 `docs/ADR_PYDANTIC_AI_RUNTIME.md` 为准。

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
   Browser Explorer 内部的页面摘要和有界动作循环也已迁移为 typed Agent/tool，
   不再直接调用 OpenAI-compatible SDK，也不再由项目手写模型决策循环。
4. filing risk 与 supplier relation 使用 typed Pydantic AI output。
5. requirement decomposition、supplier proposal、node profile 分别使用专用的
   `RequirementDecomposition`、`SupplierProposalBatch`、`NodeProfileBatch`
   Pydantic AI output；supplier relation 也只接受 typed client。通用 JSON Agent、
   字符串 completion 兼容和手工 JSON 恢复逻辑已删除。
6. `AGENT_RUNTIME_MODE` 已退役；旧环境值被忽略，不能恢复已删除代码。
7. 旧持久化记录的 `legacy`、`pydantic_ai_shadow`、
   `pydantic_ai_primary` 值仍可解析；新 run 统一写入 `pydantic_ai`。
8. API 的 `tool_loop_mode` 字段仅为旧客户端 wire compatibility 保留并忽略。
9. FinRisk 与 Supply Chain 的 API、CLI 和后台任务已统一使用 Pydantic Graph
   默认入口，旧的手写 step 循环已删除。
10. filing/transcript/web 通用 extraction 已删除任意 `parse`/`complete` client
    兼容和手工 JSON 恢复逻辑；显式传入 `LLMRunConfig` 时统一构建 typed
    Pydantic AI extraction client，未传入时保持离线模式。
11. `/agent-runs` 的 planner/subgoal 外层循环已迁移到 Pydantic Graph；预算、
    evidence normalization、human review 与持久化合同保持不变。
12. 原占位 typed Agents 已完成收敛：generic extraction Agent 已接入
    filing/transcript/web client；未被生产路径使用的 graph interpretation 与
    report generation builders 已删除。图事实解释和最终安全报告继续使用可审计的
    确定性实现。
13. 以下实现及其专用测试已删除：
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

同日另行执行 Browser Explorer 与 generic extraction live smoke：Browser Agent
实际调用 1 次 `browser_action` tool，并返回经 `BrowserAction` 校验的 `search`
动作；generic extractor 返回 typed `ExtractionResult`，结果通过。

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
P0 typed supply-chain 收敛后的全量后端回归为 `991 passed, 6 skipped`；frontend
最近一次验证为 18 个测试文件、76 项测试通过，production build 通过。

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
