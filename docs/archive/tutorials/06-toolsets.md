# Chapter 6：理解当前 Model、Deps 与 Typed Toolsets 边界

> 当前实现导读。本文按 `main` 的 `558e276f7880b081f64c4fecabdadc7212e3db59`
> 复核，描述已经存在的代码，而不是要求重新创建另一套 `src/ai/tools/`。

## 本章结果

完成本章后，你应能沿着当前代码回答四个问题：

1. 一次请求如何从 `LLMRunConfig` 解析为 Pydantic AI `Model`；
2. run identity、权限、预算和服务如何进入 `AgentDeps`；
3. 13 个项目工具怎样由 typed Python 函数生成 schema；
4. 为什么工具在“模型可见性”和“真正执行”两个位置都要检查权限。

当前仓库已经完成 Pydantic AI cutover。不要再创建 legacy/shadow/primary runtime，也不要按
旧版教程拆出尚不存在的 `src/ai/tools/{market,filing,...}.py`。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/ai/model_factory.py` | 解析 `sglang`、`vllm`、`deepseek`、`openai`，构造 `OpenAIChatModel` |
| `src/schemas/llm_config.py` | 定义单次请求可覆盖的 provider、base URL 和 model |
| `src/ai/deps.py` | 定义 subject、permissions、services、budget 和 conversation identity |
| `src/tools/contracts.py` | 保留项目 tool catalog 的 callable、scope、risk 和旧 OpenAI schema 合同 |
| `src/tools/catalog.py` | 组装当前 13 个业务工具及 backend callable |
| `src/ai/toolsets.py` | 为 catalog 中的工具选择 typed wrapper，过滤权限并记录执行事件 |
| `src/ai/usage.py` | 把现有 `AgentBudget` 映射为 request/tool-call limits |
| `src/ai/runtime_types.py` | 保存 workflow 消费的 tool-run result 合同 |
| `src/ai/smoke.py` | 用 typed output 验证最小 Agent 边界 |

本章最重要的现实约束是：当前实现仍保留 `ProjectTool.parameters`，供项目 catalog 和历史测试
使用；Pydantic AI 的实际 tool schema 则来自 `src/ai/toolsets.py` 中的函数签名。
`tests/ai/test_toolsets.py` 还会检查两者的字段 parity。它是当前兼容约束，不应被描述成已经删除。

## 6.1：从请求配置到 Model

当前公共调用形式是：

```python
config = resolve_agent_model_config(run_config, settings=settings)
model = build_agent_model(config)
```

`resolve_agent_model_config` 的实际签名是：

```text
resolve_agent_model_config(
    run_config: LLMRunConfig | None = None,
    *,
    settings: Settings | None = None,
) -> AgentModelConfig
```

学习时重点检查：

- `_OpenAICompatibleConfig` 使用 `extra="forbid"` 和 `frozen=True`；
- base URL 会去掉尾部 `/`，并拒绝非 HTTP(S) 或无 host 的地址；
- API key 使用 `SecretStr`，避免普通 `repr` 泄漏；
- DeepSeek 会拒绝空值和 placeholder key；
- 未知 `LLM_PROVIDER` 立即失败；
- 四个 provider 最终都通过 `OpenAIProvider` 和 `OpenAIChatModel` 接入；
- 非 OpenAI endpoint 使用保守的 `OpenAIModelProfile`，关闭未确认支持的 strict schema/tool choice。

当前 `temperature`、`max_tokens` 主要由具体 Agent/client 的 `model_settings` 管理，而不是统一
放进 `AgentModelConfig`。修改这一点会影响多个调用方，应作为单独设计变更，不要在教程练习中
顺手迁移。

对应测试：

```bash
uv run python -m pytest -q tests/ai/test_model_factory.py tests/test_config.py
```

## 6.2：单次 run 的 typed dependencies

当前 `AgentDeps` 包含：

```text
run_id
conversation_id
load_message_history
settings
subject
permissions
budget
services
```

其中：

- `AgentSubject` 保存 ticker、company、product 和少量 metadata；
- `AgentPermissions` 根据 `ProjectTool.scopes` 与 `risk_level` 判断是否允许；
- `AgentServices` 注入 catalog、search router、trace/evidence sink、message recorder；
- `tool_events` 使用 `default_factory=list`，确保不同 run 不共享事件；
- `AgentBudget` 仍是项目业务状态的一部分；
- `Settings` 当前确实位于 deps 中，这是当前实现事实，不能按理想化设计写成“不存在”。

所有权规则仍然必须成立：

- `run_id` 由 API/workflow 创建；
- `conversation_id` 从服务端 run state 恢复；
- permission 由 composition root 构造，不能由 prompt 自报；
- model 在 Agent 构造时选择，不放进 deps；
- service 实例由 API、pipeline 或测试注入。

`visible_tool_catalog()` 是便捷的确定性过滤入口。无 catalog 时返回空 catalog，而不是隐式构造
网络服务。

## 6.3：当前 typed toolset 的真实结构

`src/ai/toolsets.py` 集中定义 13 个 typed wrapper：

```text
market:     web_search, web_fetch, search_and_fetch
filing:     sec_list_filings, sec_fetch_filing, transcript_lookup,
            management_snapshot_lookup
financial:  financial_metrics_lookup, xbrl_fact_lookup,
            financial_snapshot_lookup
graph:      graph_query, graph_path_search
browser:    browser_explore
```

参数范围通过 `Annotated` 和 `Field` 表达，例如：

```python
ResultsLimit = Annotated[int, Field(ge=1, le=10)]
Quarter = Annotated[int, Field(ge=1, le=4)]
HopLimit = Annotated[int, Field(ge=1, le=4)]
BrowserSteps = Annotated[int, Field(ge=1, le=10)]
```

`build_project_function_toolset(catalog)` 做三件事：

1. 按工具名从 `_TYPED_TOOLS` 找 typed wrapper；
2. 由函数签名生成 Pydantic AI schema；
3. 把 catalog 的 scopes、risk、evidence kind、result limit 放入 metadata。

如果 catalog 出现没有 typed wrapper 的工具，构造立即失败。这样新增工具时必须同时补 typed
边界，不能悄悄退化为任意参数调用。

## 6.4：可见性与执行时权限

当前权限链是：

```text
ToolCatalog.for_scope(scope)
  -> build_project_function_toolset
  -> FilteredToolset 根据 ctx.deps.permissions 隐藏工具
  -> _invoke_project_tool 再次检查 permissions.allows(project_tool)
```

两次检查承担不同职责：

- filtering 减少模型可以看到和选择的工具；
- execution-time check 是真正的安全边界，防止直接 `call_tool` 或错误组合绕过。

`interactive` 工具要求 `allow_interactive=True`；`write_gated` 工具要求
`allow_write=True`。当前 API 构造普通 Agent run 时两者都为 `False`。

## 6.5：执行、envelope、截断与 trace

`_invoke_project_tool` 当前按以下顺序工作：

```text
从注入 catalog 查找 ProjectTool
→ 再次检查权限
→ asyncio.to_thread(project_tool.executable(), **arguments)
→ 校验 ToolResultEnvelope
→ 生成 ToolExecutionEvent
→ 追加到 deps.services.tool_events
→ 可选发送 trace_sink
```

当前 `ToolResultEnvelope.status` 只有 `success | failed`。权限拒绝和 backend 异常会成为
`failed`，具体类型保留在 `error` 字符串中。不要在文档中宣称已经存在 `denied` 或 `timeout`
枚举。

截断由 `ProjectTool.executable()` 调用 `truncate_jsonable()` 完成。工具执行事件记录 latency、
result chars 和 truncated 状态。当前 wrapper 始终把 catalog callable 放入 worker thread；它主要
面向现有同步业务 backend。

## 6.6：预算的当前映射

`build_usage_limits()` 当前只映射：

```text
request_limit = max_subgoals * (max_tool_rounds_per_subgoal + 1)
tool_calls_limit = max_total_tool_calls
```

token limit 尚未进入 `AgentBudget`。`max_total_fetch_pages`、wall-clock 和总结果字符仍由领域层或
runtime 管理。这是当前能力边界，不要把旧教程中“input/output/total token 均已映射”当成事实。

## 6.7：练习与验收

推荐先阅读测试，再手写一个最小同构 wrapper：

1. 给函数写明确参数类型；
2. 把它加入 `_TYPED_TOOLS`；
3. 在 catalog 中加入 callable 与 governance metadata；
4. 验证 schema、可见性、直接绕过拒绝和 trace；
5. 不连接真实 SEC、Neo4j、浏览器或模型服务。

运行当前章节相关检查：

```bash
uv run ruff check \
  src/ai/model_factory.py src/ai/deps.py src/ai/toolsets.py \
  src/ai/usage.py src/ai/smoke.py
uv run python -m pytest -q \
  tests/ai/test_model_factory.py \
  tests/ai/test_deps.py \
  tests/ai/test_toolsets.py \
  tests/ai/test_usage.py \
  tests/ai/test_smoke.py
```

- [ ] 能解释 catalog schema 与 typed wrapper schema 为什么暂时共存。
- [ ] 能证明浏览器工具在可见性和执行阶段都会被拒绝。
- [ ] 能指出当前 envelope 和 usage mapping 尚未表达哪些状态。
- [ ] 没有新建第二套 tool package 或 runtime。

下一章继续沿真实调用链学习 typed Agents、兼容 adapters 和 Pydantic Graph。
