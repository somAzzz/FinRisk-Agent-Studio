# Chapter 2：用 Typed Dependencies 表达单次运行上下文

> 当前实现导读。`AgentDeps` 的目标不是容纳整个应用，而是把本次 Agent run 所需的 identity、
> subject、权限、预算和最小服务显式注入。

## 本章结果

完成本章后，你应能解释：

- `run_id`、`conversation_id` 和 subject 的不同含义；
- permission 为什么不能从 prompt 生成；
- `AgentServices` 中哪些对象是 capability，哪些是 per-run mutable state；
- planner、toolset、browser 和 message recorder 如何消费 deps；
- 当前实现为何没有广泛使用 dynamic instructions。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/ai/deps.py` | 共享 `AgentSubject`、`AgentPermissions`、`AgentServices`、`AgentDeps` |
| `src/agents/state.py` | `AgentBudget` 与 run/subgoal state |
| `src/ai/planner_adapter.py` | 从 `AgentRunState` 构造 planner deps |
| `src/ai/toolsets.py` | 从 `RunContext[AgentDeps]` 读取权限和 services |
| `src/ai/browser_client.py` | `BrowserToolDeps = AgentDeps + guarded browser session` |
| `src/ai/runtime_adapter.py` | 使用 conversation/history/budget/services 运行 Agent |
| `src/api/agent_runs.py` | 生产 composition root，创建 model、catalog、permissions 和 deps |

## 2.1：四层依赖对象

### `AgentSubject`

保存本次研究对象：ticker、company、product 和少量 metadata。它不负责加载公司、连接数据库或
保存全局用户状态。

### `AgentPermissions`

保存：

```text
tool_scopes
allow_interactive
allow_write
```

`allows(ProjectTool)` 统一检查 scope 与 risk。普通 API Agent run 当前显式设置 interactive/write
为 `False`。

### `AgentServices`

当前可注入：

```text
search_router
tool_catalog
evidence_sink
trace_sink
tool_events
message_recorder
```

所有字段都允许为空，使不需要工具或持久化的 typed Agent 可以在离线测试中运行。

### `AgentDeps`

将 run identity、settings、subject、permissions、budget 和 services 组合成一次运行的对象图。
model 不在 deps 中；它在 Agent builder/composition root 中显式选择。

## 2.2：Identity 的所有权

```text
run_id           一次具体执行
conversation_id  多次执行共享的可信对话身份
subject          本次业务研究对象
```

API 创建 run ID；resume 创建新的 run ID 并沿用服务端保存的 conversation ID。客户端 prompt 不应
提供任意 conversation history，也不能选择另一个 tenant 的 conversation ID。

`conversation_id=None` 时，runtime adapter 使用 `run_id` 作为默认 conversation identity。

## 2.3：权限是依赖，不是提示词

工具安全链：

```text
authenticated/API policy
  -> AgentPermissions
  -> visible_tool_catalog / FilteredToolset
  -> model 只看到允许工具
  -> _invoke_project_tool 再次 permissions.allows
```

即使 instructions 告诉模型“不要用 browser”，也不能替代 `allow_interactive=False`。反过来，
prompt 要求“开启写权限”也不会修改 deps。

planner 的 output validator 同样从 `ctx.deps.permissions` 读取允许 scopes，并用
`visible_tool_catalog()` 检查 selected tools。

## 2.4：Mutable default 必须按 run 隔离

`AgentServices.tool_events` 使用：

```python
tool_events: list[ToolExecutionEvent] = field(default_factory=list)
```

如果写成 `[]` 共享默认值，不同用户/run 的 trace 会互相污染。`AgentSubject.metadata`、permissions
集合、budget 和 services 同样通过 factory 创建安全默认值。

## 2.5：Browser 使用更窄的 deps

`BrowserToolDeps` 没有把 Playwright 或完整 Browser Explorer 塞进通用 deps，而是组合：

```text
agent_deps: AgentDeps
session: BrowserToolSession
```

`browser_action` 只能调用 `session.execute(BrowserAction)`。浏览器策略、步骤限制和 I/O 仍由受控
session/Explorer 负责，模型不能取得任意浏览器对象。

## 2.6：当前没有广泛使用 dynamic instructions

FinRisk 已使用 typed deps，但业务上下文主要进入显式 prompt：

- planner prompt 包含 goal、pending subgoal、accepted evidence 和可用工具；
- filing prompt 包含 company、year、source 和 chunk；
- supply-chain step 负责构造自己的任务 prompt；
- deps 主要控制权限、服务、预算、identity、history 和 output validation。

这是当前设计事实。未来可以为稳定、可信且每次运行变化的上下文使用
`@agent.instructions` + `RunContext`，但不应为追求形式把用户原文或大型 evidence 全塞进 deps。

## 2.7：Composition root 示例路径

阅读 `src/api/agent_runs.py::_build_pydantic_agent_runtime()`：

```text
AgentRunRequest
  -> Settings + LLMRunConfig
  -> model_factory
  -> project ToolCatalog
  -> AgentRunRecorder
  -> PydanticAIPlanner
  -> per-subgoal AgentDeps
  -> PydanticAIRuntimeAdapter
  -> GlobalAgentRuntime
```

它是理解“对象在哪里创建、由谁拥有”的最佳入口。Agent 模块本身不在 import 时创建全局 model。

## 2.8：练习与验收

```bash
uv run python -m pytest -q \
  tests/ai/test_deps.py \
  tests/ai/test_planner_adapter.py \
  tests/ai/test_runtime_adapter.py \
  tests/ai/test_browser_client.py \
  tests/api/test_agent_runs_api.py
```

推荐练习：构造两个 `AgentDeps`，让它们使用不同 scope 和独立 `AgentServices`，验证可见工具和
`tool_events` 不互相影响。

- [ ] run、conversation 和 subject identity 没有混淆。
- [ ] permissions 由服务端构造，不从模型输出恢复。
- [ ] browser session 通过窄 Protocol 注入。
- [ ] mutable event list 是 per-run。
- [ ] model 不属于 deps。
- [ ] 能准确说明当前 dynamic instructions 的使用范围。

下一章继续讨论结构合法之后，如何处理语义校验、重试、失败和并发。
