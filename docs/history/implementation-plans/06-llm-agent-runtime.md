# Step 06 - 本地 LLM Agent Runtime

## 目标

把当前单一 LLM client 和工具路由升级为可扩展 Agent Runtime。它不需要一次性实现所有智能行为，但必须建立统一执行框架。

当前相关代码：

```text
src/llm/client.py
src/llm/sglang_client.py
src/tools/router.py
src/browser/explorer.py
```

## 需要新增或修改的文件

新增：

```text
src/agents/__init__.py
src/agents/state.py
src/agents/base.py
src/agents/runtime.py
src/agents/planner.py
src/agents/critic.py
src/agents/tools.py
tests/agents/test_state.py
tests/agents/test_runtime.py
tests/agents/test_planner.py
```

修改：

```text
src/llm/sglang_client.py
src/tools/router.py
src/config.py
```

## Agent State

```python
class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result_summary: str | None = None
    success: bool | None = None
    created_at: datetime

class AgentState(BaseModel):
    goal: str
    ticker: str | None = None
    company_name: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tool_history: list[ToolCall] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    max_steps: int = 10
    current_step: int = 0
```

## Agent Base

```python
class Agent(Protocol):
    name: str

    def run(self, state: AgentState) -> AgentState:
        ...
```

或 async 版本：

```python
class AsyncAgent(Protocol):
    name: str

    async def run(self, state: AgentState) -> AgentState:
        ...
```

建议优先同步，遇到已有 async 工具时在 runtime 中兼容。

## PlannerAgent

职责：

- 根据 goal 决定下一步需要哪个 agent 或工具。
- 输出结构化 plan。

Schema：

```python
class PlanStep(BaseModel):
    step_id: str
    action: Literal[
        "fetch_filing",
        "fetch_transcript",
        "web_search",
        "extract_entities",
        "extract_relations",
        "write_graph",
        "analyze_risk",
        "analyze_sentiment",
        "discover_opportunity",
        "finish",
    ]
    reason: str
    inputs: dict[str, Any] = Field(default_factory=dict)

class AgentPlan(BaseModel):
    steps: list[PlanStep]
    needs_more_info: bool
```

初版可用规则生成，不必完全依赖 LLM：

- 有 ticker 且无 filing evidence -> fetch_filing
- 有 filing 且无 entity -> extract_entities
- 有 entity 且无 relation -> extract_relations
- 有 relation 且无 graph -> write_graph
- 最后 discover_opportunity

## AgentRuntime

```python
class AgentRuntime:
    def __init__(
        self,
        agents: dict[str, Agent],
        tools: ToolRegistry,
        planner: PlannerAgent,
        critic: CriticAgent | None = None,
    ):
        ...

    def run(self, goal: str, ticker: str | None = None) -> AgentState:
        ...
```

要求：

- 限制最大步数。
- 每一步记录 tool/agent history。
- agent 失败时记录错误，不直接崩溃，除非是不可恢复错误。
- final state 包含 claims/evidence。

## Tool Registry

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None:
        ...

    def call(self, name: str, **kwargs) -> ToolResult:
        ...
```

ToolResult：

```python
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    content: Any = None
    error: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
```

## CriticAgent

初版规则：

- Claim 没有 evidence -> 降低 confidence 或标记 invalid。
- Evidence quote 为空 -> invalid。
- Claim confidence > 0.9 但 evidence 少于 2 条 -> 降到 0.8 以下。

后续可接 LLM。

## 测试策略

用 fake agent 和 fake tool 测试 runtime。

测试覆盖：

- runtime 最大步数生效。
- planner 生成 plan。
- tool history 被记录。
- agent failure 被记录。
- critic 会降低无证据 claim 的 confidence。
- final state 可 JSON 序列化。

## 验收标准

- 可以运行一个 fake 端到端 AgentRuntime。
- 不依赖真实 LLM 和外部 API。
- 后续步骤可注册真实 Agent。

## 给执行助手的注意事项

- 本步骤不要实现复杂金融分析。
- Agent 框架要小而清晰，不要引入大型外部 agent 框架，除非用户明确要求。
- 当前项目目标是本地可控，不要强绑定云服务。

