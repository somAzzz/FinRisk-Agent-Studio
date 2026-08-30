# Chapter 6：建立新的 Model、Deps 与 Typed Toolsets 边界

## 本章结果

本章先建立一条不依赖旧 tool loop 的 Pydantic AI 最小运行路径：集中构造模型、每次
run 注入 typed dependencies、由 typed Python 函数生成工具 schema，并在可见性和执行
两个阶段实施权限。

旧 runtime 在本章末暂时还存在，只用于让尚未迁移的调用方继续工作；Chapter 7 必须
完成切换并删除它。不要添加 feature flag，也不要写新旧 runtime adapter。

前置条件：已按教程首页从 `023c02f91be43ecf6428d12e5dac3272569a62b3`
创建学习分支，并记录迁移前全量测试结果。

## 设计决定

1. Python 类型签名是工具输入 schema 的真相源；不复制旧 `ProjectTool.parameters`。
2. `AgentDeps` 是单次 run 的对象图，不是全局 service locator。
3. 工具返回统一 envelope，但业务数据保留结构，不拼成自由文本。
4. scope filtering 控制模型“看见什么”；执行时 permission check 控制“实际能做什么”。
5. provider 只在 model factory 中解析；Agent 和业务 workflow 不读取 provider 环境变量。

## 文件变更总览

### 新建文件

| 文件 | 必须实现的职责 | 接替的旧职责 |
| --- | --- | --- |
| `src/ai/__init__.py` | 只导出稳定公共边界，不在 import 时构造模型 | 消除业务模块从多个 `src/llm/*` 猜入口 |
| `src/ai/model_factory.py` | 校验 provider 配置并返回 Pydantic AI `Model` | 替代 `client.py`、`deepseek_client.py`、`sglang_client.py` 中分散的 client 构造 |
| `src/ai/deps.py` | 定义 subject、permissions、services、budget 与 `AgentDeps` | 替代全局对象和闭包中隐式传递的运行时状态 |
| `src/ai/runtime_types.py` | 定义 workflow 与 Agent 边界共享的最小结果类型 | 替代 workflow 对旧 tool-loop 内部 result 类型的依赖 |
| `src/ai/tools/__init__.py` | 导出 tool envelope 和各领域 toolset builder | 新的 typed tools 包入口 |
| `src/ai/tools/models.py` | 定义 `ToolResultEnvelope` 与稳定失败语义 | 替代每个旧工具各自返回 dict/string/exception |
| `src/ai/tools/invoke.py` | 执行权限复核、sync-to-thread、异常转换、截断和 trace | 接替 `tool_loop.py` 中工具执行与错误处理职责 |
| `src/ai/tools/market.py` | typed `web_search`、`web_fetch`、`search_and_fetch` | 替代旧 JSON tool schema 与动态参数分派 |
| `src/ai/tools/filing.py` | typed SEC filing、transcript tools | 同上，限定 filing/transcript 参数 |
| `src/ai/tools/financial.py` | typed metrics、XBRL、snapshot tools | 同上，限定数值/period 参数 |
| `src/ai/tools/graph.py` | typed graph query/path tools | 同上，限制 hop 与 edge type |
| `src/ai/tools/browser.py` | typed interactive browser tool | 从普通 read tool 中分离高风险 capability |
| `src/ai/toolsets.py` | 组合 domain toolsets，并按 run 动态过滤 | 替代旧 loop 向所有 Agent 暴露统一工具表 |
| `src/ai/usage.py` | 把 `AgentBudget` 映射为 `UsageLimits` | 替代手写循环中的分散计数/停止判断 |
| `src/ai/smoke.py` | 最小 typed Agent smoke；禁止导入旧 runtime | 提供新边界独立可运行的证据 |

### 修改文件

| 文件 | 修改内容 | 原因 |
| --- | --- | --- |
| `pyproject.toml`、`uv.lock` | 添加并锁定 `pydantic-ai-slim[openai]` | 依赖必须可复现 |
| `src/config.py` | 增加 discriminated provider config 或等价的严格配置 | 禁止业务层拼 base URL、model、key |
| `src/agents/state.py` | 只在现有 `AgentBudget` 缺少 request/tool/token 上限时补充字段 | 业务预算与框架 usage limit 需要明确映射 |
| `.env.example` | 记录各 provider 所需变量，不填真实密钥 | 配置合同可发现且不泄露凭据 |
| `tests/conftest.py` | 默认禁止真实模型请求 | 单元测试不能因漏 mock 访问网络 |

### 新建测试

```text
tests/ai/
  __init__.py
  test_model_factory.py
  test_deps.py
  test_tool_models.py
  test_tool_execution.py
  test_toolsets.py
  test_usage.py
  test_smoke.py
```

本章不删除旧文件；删除清单在 Chapter 7。

## 6.1：集中式 model factory

`src/ai/model_factory.py` 至少提供两个公共合同：

```text
resolve_agent_model_config(settings, run_config=None) -> AgentModelConfig
build_agent_model(config) -> Model
```

配置需表达 `sglang`、`vllm`、`deepseek`、`openai` 四种 provider，并校验：

- base URL 只能是 `http` / `https` 且非空；
- model name 非空；
- timeout、temperature、max tokens 有合理边界；
- API key 不进入 repr、日志和异常；
- OpenAI-compatible provider 使用 Pydantic AI provider/model 对象，不返回裸 SDK client；
- 未知 provider 立即失败，不静默回落到默认模型。

`tests/ai/test_model_factory.py` 必须覆盖每个 provider、非法 URL、空 model、缺失 key 的
策略以及 secret redaction。测试只检查构造和配置，不发网络请求。

## 6.2：设计单次 run 的 typed dependencies

`src/ai/deps.py` 建议分为四层：

```text
AgentSubject       本次研究对象，不含全局状态
AgentPermissions   scope、interactive、write 权限
AgentServices      tool backend、evidence sink、trace sink、message store
AgentDeps          run_id、conversation_id、subject、permissions、budget、services
```

服务用 `Protocol` 描述最小行为。不要把 FastAPI request、完整 Settings、数据库连接池和
所有仓库对象无差别塞进 deps；Agent 只获得完成任务所需的最小 capability。

必须写清以下所有权：

- `run_id` 由 application layer 创建；
- `conversation_id` 只能从受信任的服务端状态恢复；
- permissions 由认证后的 principal/tenant policy 生成，不能由 prompt 生成；
- services 由 composition root 注入；
- model 不是 deps 的一部分，由 Agent 构造阶段选择；
- mutable event collection 是 per-run，禁止作为 dataclass 的共享默认值。

## 6.3：统一工具返回与失败语义

`ToolResultEnvelope` 至少包含：

```text
tool, status, data, evidence_kind, warnings, truncated, error
```

要求 `extra="forbid"`。`status` 至少区分 `success` 与 `failed`；如果你还需要
`denied`、`timeout`，应在本章确定并贯穿 trace/eval，不能靠解析 error string 判断。

`invoke.py` 的执行次序必须固定：

```text
解析 tool spec
  -> execution-time permission check
  -> 校验/接收 typed arguments
  -> sync backend 放入 worker thread，async backend 直接 await
  -> 转成 JSON-safe data
  -> 按 max_result_chars 处理上下文返回
  -> 记录 success/failure event
  -> 返回 envelope
```

异常对模型只暴露稳定类型和安全消息；完整 traceback 留在受控日志，不进入 prompt。
权限拒绝、backend 失败和结果截断都必须产生 trace event。

## 6.4：按领域编写 typed tools

每个工具函数必须：

- 显式声明参数类型、范围和 `RunContext[AgentDeps]`；
- docstring 说明模型何时应该调用，而不是描述内部实现；
- 只通过 `ctx.deps.services` 访问 backend；
- 返回 `ToolResultEnvelope`；
- 不读取环境变量、不创建数据库连接、不自己选择 provider；
- 不接受 `**kwargs` 或任意 dict 逃逸 typed schema。

参数约束示例：搜索结果 1–10、filing 数量 1–20、quarter 1–4、graph hops 1–4、
browser steps 1–10。具体值可以调整，但必须由业务风险和上下文预算解释。

旧 `ProjectTool.parameters` 可以在过渡期继续服务尚未迁移的旧 loop，但新 tool schema
不得从它生成，也不写 parity test。Chapter 7 删除旧 loop 后，再判断 `ProjectTool`
是否仍被非 LLM 调用方需要；无调用方就删除其 schema 部分。

## 6.5：静态分域与动态权限

`src/ai/toolsets.py` 负责两个不同问题：

1. 静态分域：filing、market、financial、graph、browser 各自有哪些工具；
2. 动态权限：这一次 run 的 principal 是否可见、可交互、可写。

建议公开：

```text
build_domain_toolset(domain) -> AbstractToolset[AgentDeps]
build_scoped_toolset(domains) -> AbstractToolset[AgentDeps]
```

不得让 coordinator 默认获得 browser/write 工具。browser 必须同时满足 domain 被选择和
`allow_interactive=True`。未来写工具还必须满足 `allow_write=True` 与 Chapter 9 审批。

模型可见性过滤不是安全边界。`invoke.py` 必须再次检查相同权限，以抵御旧 schema 缓存、
直接 `call_tool`、错误组合 toolset 或未来重构造成的绕过。

## 6.6：预算映射

`src/ai/usage.py` 只负责把框架能执行的限制映射到 `UsageLimits`：requests、tool calls、
input/output/total tokens。公司数量、来源数量、graph path 数量和 wall-clock deadline 是
领域预算，继续留在 application/workflow state。

测试必须证明：

- `None` 保持不限，不被错误映射成 0；
- 负数或 0 的策略明确；
- framework limit 与 domain budget 不共享同一个含义模糊的 `max_steps`；
- 超限是可识别的运行失败，不伪装成 provider error。

## 6.7：测试矩阵

| 测试文件 | 最低覆盖 |
| --- | --- |
| `test_model_factory.py` | provider 解析、非法配置、secret redaction、无网络构造 |
| `test_deps.py` | 默认值隔离、scope 组合、interactive/write 拒绝、缺失 service |
| `test_tool_models.py` | extra fields、JSON-safe data、稳定 failure contract |
| `test_tool_execution.py` | sync/async backend、异常、timeout、truncate、success/failure trace |
| `test_toolsets.py` | 每个 specialist 只看允许工具；直接绕过仍拒绝；duplicate name 失败 |
| `test_usage.py` | 所有 limit 映射和边界值 |
| `test_smoke.py` | `TestModel` 下 typed output + 一次工具调用；不导入 `src.llm` |

使用 `TestModel` 检查工具曝光和 schema；使用 `FunctionModel` 精确控制调用路径。不要用
`TestModel` 评价金融答案质量，也不要在单元测试中连接 SEC、Neo4j、浏览器或模型服务。

## 本章验收

```bash
uv run ruff check src/ai tests/ai
uv run pytest -q tests/ai
uv run python -m src.ai.smoke
```

然后人工确认：

- [ ] 新 smoke 在不导入旧 runtime 的情况下完成一次 typed run。
- [ ] typed 函数签名而非旧 JSON schema 是工具合同真相源。
- [ ] 可见性过滤与执行时权限都生效。
- [ ] provider、deps、tool execution、usage 职责没有混在一个类中。
- [ ] 没有新增 legacy/shadow/primary feature flag。
- [ ] 已记录 Chapter 7 必须迁移和删除的剩余旧调用方。

本章建议提交：

```text
ch06: establish typed model deps and tool boundaries
```
