# Chapter 0：让唯一模型边界只负责 Deployment Policy

> 本章以当前 `main` 为准，解释已落地的 model factory 与 generation policy
> 职责分离。项目保留自己的 factory，但它只处理 Pydantic AI 不知道、也不应该
> 知道的部署策略。

## 本章结果

完成本章后，你应能建立四个互不混淆的边界：

```text
Model factory       where / what model
ModelSettings       how to generate
Agent               what task
UsageLimits/Graph   how much work is allowed
```

并能解释：

- 为什么 request-level provider override 不应修改 `os.environ`；
- 为什么 timeout 必须可以证明真正到达 `ModelSettings`；
- 为什么当前 DeepSeek 只支持官方 endpoint，并显式拒绝自定义地址；
- 为什么官方 OpenAI 与 local OpenAI-compatible endpoint 不应共享含混默认值；
- live capability acceptance 与金融质量 eval 为什么是两套证据。

## 当前评价

当前 Chapter 0 的核心职责分离已落地。

已完成：

- `Settings -> LLMRunConfig -> discriminated AgentModelConfig -> model factory`；
- 不通过 request 修改全局环境变量；
- request-level provider/model/base URL override；
- frozen config、`extra="forbid"` 和 `SecretStr`；
- provider 与 URL 的提前校验；
- 非 OpenAI endpoint 的 conservative `ModelProfile`；
- 默认 `ALLOW_MODEL_REQUESTS=False`；
- `FunctionModel` 离线验收和独立 live acceptance；
- CLI 错误脱敏和非零失败退出码。
- generation semantics 已从 provider config/factory 移入独立 `AgentGenerationConfig`；
- application、Agent 和 run 三层设置通过 `merge_model_settings()` 按优先级合并；
- timeout 已在 `PydanticAIRuntimeAdapter` 的 run boundary 传入模型；
- OpenAI 默认 endpoint 已改为官方 URL，云端占位 key 会在联网前失败；
- DeepSeek 官方 endpoint 使用 `DeepSeekProvider`，自定义 endpoint 显式拒绝；
- 未使用的 `llm_model` 和 provider-specific generation 字段已删除。

后续可选改进：

1. 在 Chapter 1 为不同 typed Agent 定义 task-specific defaults；
2. 若产品确实需要 DeepSeek 代理，增加独立的 custom-endpoint provider 类型和 trace 证据；
3. 只在 capability test 证明需求时引入 `OpenAIResponsesModel`；
4. 将 live acceptance 从合成 smoke 扩展为独立 capability probes；
5. `pydantic-settings` 可以减少环境解析样板，但不是本章前提。

## 当前文件地图

| 文件 | 当前职责 | 实现状态 |
| --- | --- | --- |
| `src/config.py` | 环境变量、provider 与 application generation 默认值 | 已分离部署与生成语义 |
| `src/schemas/llm_config.py` | per-run deployment 与独立 generation schema | 已分离 |
| `src/ai/model_settings.py` | application/Agent/run 设置映射与合并 | 已实现 |
| `src/ai/model_factory.py` | 解析配置并构造 `OpenAIChatModel` | 只负责 provider/model/endpoint/profile |
| `src/ai/runtime_adapter.py` | 在 run boundary 汇合 `ModelSettings` 和 `UsageLimits` | 已实现 |
| `src/ai/live_acceptance.py` | typed output + local tool 合成验收 | 扩展成可定位的 capability report |
| `scripts/pydantic_ai_live_acceptance.py` | 真实 provider CLI | 保持显式运行和错误脱敏 |
| `tests/conftest.py` | 禁止默认真实请求 | 保持不变 |

## 0.1：目标结构

```text
.env / deployment configuration
  -> Application Settings
       endpoint / credential / infrastructure defaults
  -> LLMRunConfig
       provider / model / base_url override
  -> resolve_agent_model_config
       validated + frozen discriminated config
  -> build_agent_model
       provider + model class + capability profile
  -> Pydantic AI Model

GenerationSettings
  -> build_model_settings
       temperature / max_tokens / timeout / thinking
  -> Agent default model_settings
  -> optional run-level override

Agent
  -> instructions / output type / tools / task

UsageLimits + workflow/Graph state
  -> requests / tool calls / tokens / domain work / deadline
```

模型对象和生成参数最终会在 `Agent.run()` 汇合，但它们的配置来源、验证和所有权必须分开。

## 0.2：Factory 只管 where / what model

当前 factory 的正确核心合同应保留：

```text
resolve_agent_model_config(run_config, *, settings)
    -> AgentModelConfig

build_agent_model(config)
    -> Model
```

`AgentModelConfig` 只应表达部署决策：

```text
provider
model
base_url（仅需要自定义 endpoint 的 provider）
api_key
provider/profile compatibility metadata
```

它不应表达：

```text
temperature
max_tokens
thinking level
tool-call budget
retry count
workflow deadline
```

这些字段与“模型部署在哪里”没有同一生命周期。把它们混进 provider config 会导致更换任务 prompt
或一次 run 的温度时必须重建部署配置，也会让 factory 同时承担 generation policy。

## 0.3：ModelSettings 管 how to generate

当前锁定的 Pydantic AI 2.27.1 中，`ModelSettings` 可以表达：

```text
temperature
max_tokens
timeout
thinking
top_p / top_k
parallel_tool_calls
seed
其他 provider-supported generation options
```

建议新增一个项目级 Pydantic 配置对象，例如 `AgentGenerationConfig`，再显式映射：

```python
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.settings import ModelSettings, ThinkingLevel


class AgentGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    thinking: ThinkingLevel | None = None


def build_model_settings(config: AgentGenerationConfig) -> ModelSettings:
    settings: ModelSettings = {}
    if config.temperature is not None:
        settings["temperature"] = config.temperature
    if config.max_tokens is not None:
        settings["max_tokens"] = config.max_tokens
    if config.timeout_seconds is not None:
        settings["timeout"] = config.timeout_seconds
    if config.thinking is not None:
        settings["thinking"] = config.thinking
    return settings
```

当前 `ThinkingLevel` 还包含布尔值与 `xhigh` 等合法取值；直接复用框架类型，避免项目复制一份
不完整的枚举。映射时只写入非 `None` 字段，使“没有 override”和显式数值保持不同语义。

### 推荐优先级

```text
run override
  > Agent-specific default
  > application generation default
  > provider/model native default
```

不要用“值为 falsy”判断 override；`None` 才表示未提供。

### timeout 放在哪里

生成请求的总 timeout 可以进入 `ModelSettings(timeout=...)`。若还需要连接池、connect/read/write
等 transport 级 timeout，则由 factory 创建受控 `httpx.AsyncClient` 并注入 provider。

两种 timeout 不能只在 `Settings` 中存在却不被消费。测试必须检查它最终进入 model settings 或
HTTP client，而不是只检查 config 字段值。

## 0.4：Provider 策略

### SGLang 与 vLLM

继续使用：

```text
OpenAIChatModel
  + OpenAIProvider(base_url=explicit local endpoint)
  + conservative OpenAIModelProfile
```

这两类部署使用 OpenAI-compatible Chat Completions protocol，但不能假定支持 OpenAI 的所有 native
capability。

### DeepSeek

Pydantic AI 2.27.1 已提供 `DeepSeekProvider`，它自带 DeepSeek model profile，包括
`reasoning_content` 和相关 tool-choice compatibility。官方 endpoint 应优先使用：

```text
OpenAIChatModel(model_name, provider=DeepSeekProvider(api_key=...))
```

当前版本的 `DeepSeekProvider` 构造参数没有 `base_url`，默认固定
`https://api.deepseek.com`。FinRisk 因此选择只支持官方 DeepSeek endpoint：环境中不再配置
`DEEPSEEK_BASE_URL`，run-level 自定义 DeepSeek URL 会在联网前显式失败。

如果未来需要代理，应建立独立、可追踪的 provider 变体，不要根据 URL 悄悄切换语义。

### OpenAI

`OPENAI_BASE_URL` 应默认使用官方 OpenAI URL，或在使用官方 `OpenAIProvider` 时不传 base URL。
它不应默认指向 SGLang，否则 `provider="openai"` 与实际部署语义不一致。

当前所有 provider 继续使用 `OpenAIChatModel` 是可接受的统一起点。只有真实需求和 capability
测试证明需要 Responses API 时，再把官方 OpenAI 分支改成：

```text
OpenAIResponsesModel + OpenAIProvider
```

local OpenAI-compatible 服务继续使用 `OpenAIChatModel`。这不是“新 API 一定更好”，而是明确
区分官方 native API 与兼容协议。

## 0.5：Agent 管 what task

Agent builder 负责：

```text
instructions
output_type
deps_type
toolsets/tools
agent name
task-specific retries/validators
task-specific default ModelSettings
```

例如 filing extraction、market research 和 browser summarization 可以拥有不同的 generation
defaults，但仍复用同一个 model factory。业务 Agent 不读取 provider 环境变量，也不根据 URL
决定 model class。

## 0.6：UsageLimits 与 workflow 管 how much work

以下限制不属于 model factory：

| 限制 | 当前/目标执行者 |
| --- | --- |
| model requests | `UsageLimits.request_limit` |
| tool calls | `UsageLimits.tool_calls_limit` |
| input/output/total tokens | `UsageLimits`，当前项目尚未完整映射 |
| subgoal 数量 | Global Agent Graph / `AgentBudget` |
| browser steps | Browser Agent + session |
| fetch pages | workflow/domain budget |
| wall-clock deadline | Graph/application infrastructure |
| tool-result chars | tool contract/runtime |

`max_tokens` 是“一次生成最多输出多少 token”，不等于整个 workflow 的 total token budget。前者是
`ModelSettings`，后者是 `UsageLimits` 或应用预算。

## 0.7：配置清理策略

### 已删除的字段

`Settings.llm_model` 没有生产调用方，已从 `Settings`、测试和 `.env.example` 删除。
DeepSeek 专用的 temperature/max-tokens/timeout 也已由通用 generation policy 取代。

### 不能直接删除的字段

`Settings.llm_provider` 仍由 `resolve_agent_model_config(None, settings=...)` 用作默认 provider。
它不是 legacy 字段。未来可以：

- 保留；或
- 重命名为语义更清楚的 `default_llm_provider`，同步环境变量和兼容期；或
- 要求所有 composition root 显式传 `LLMRunConfig` 后再删除。

不要在同一改动中既删除默认 provider，又让调用方静默使用 SGLang。

### 是否采用 `pydantic-settings`

长期使用它可以集中 env alias、SecretStr、嵌套配置和验证；但当前 `dataclass + os.environ +
lru_cache` 已能工作。只有当配置复杂度或重复验证成为维护问题时再迁移，避免让依赖替换掩盖本章
真正的职责分离。

## 0.8：Capability acceptance

默认测试继续设置：

```python
models.ALLOW_MODEL_REQUESTS = False
```

离线测试使用 `TestModel`/`FunctionModel`。真实 provider 必须由独立 CLI 显式运行，并且至少报告：

```text
provider / model / effective endpoint
typed output pass/fail
tool calling pass/fail
usage availability
latency
safe error type/message
```

当前 `run_live_acceptance()` 把 typed output 和一次本地 tool call 放在一个合成流程中，适合作为
最低 smoke。若要判断 OpenAI Responses、DeepSeek reasoning 或 local strict schema 等能力，应增加
分项 probe，而不是从一次成功推断所有 capability。

## 0.9：实现对照

> 本节展示当前已落地的关键代码。学习者可以按文末顺序在隔离分支重演，
> 但不应再把这些作为当前 `main` 的待实施清单。

### 0.9.1：只替换 `.env.example` 的 LLM 区域

保留文件中 API safety、SEC、Neo4j、cache、search 和 browser 区域，只将开头的 LLM 配置替换为：

```dotenv
# Default deployment. Request-level LLMRunConfig may override it.
LLM_PROVIDER=sglang

# Generation policy. Omitted values preserve model/provider defaults.
# LLM_TEMPERATURE=0.1
# LLM_MAX_TOKENS=2000
LLM_TIMEOUT_SECONDS=60
# LLM_THINKING=low

# Local OpenAI-compatible deployments
SGLANG_BASE_URL=http://localhost:30000/v1
SGLANG_MODEL=qwen3.8-27b
SGLANG_API_KEY=EMPTY

VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=nvidia/Qwen3.6-27B-NVFP4
VLLM_API_KEY=dummy

# DeepSeek
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=REPLACE_ME

# OpenAI
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=REPLACE_ME
```

这里故意不再提供 `DEEPSEEK_TEMPERATURE` 等 provider-specific generation 变量。`LLM_MODEL`
也不再属于应用 `Settings`；`scripts/real_data_acceptance.py` 中同名环境变量是独立 CLI 兼容项，
应在后续单独迁移。

### 0.9.2：在 `Settings` 中表达应用默认值

先增加“空字符串等于未提供”的解析函数：

```python
def _env_optional(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip() or None


def _env_optional_float(
    name: str,
    default: float | None = None,
) -> float | None:
    raw = _env_optional(name)
    return default if raw is None else float(raw)


def _env_optional_int(
    name: str,
    default: int | None = None,
) -> int | None:
    raw = _env_optional(name)
    return default if raw is None else int(raw)
```

然后在 `Settings` 中保留 `llm_provider`，删除未被生产调用方消费的 `llm_model`，并用通用生成参数
取代 DeepSeek 专用参数：

```python
llm_provider: str = field(
    default_factory=lambda: _env("LLM_PROVIDER", "sglang")
)
llm_temperature: float | None = field(
    default_factory=lambda: _env_optional_float("LLM_TEMPERATURE")
)
llm_max_tokens: int | None = field(
    default_factory=lambda: _env_optional_int("LLM_MAX_TOKENS")
)
llm_timeout_seconds: float | None = field(
    default_factory=lambda: _env_optional_float(
        "LLM_TIMEOUT_SECONDS", 60.0
    )
)
llm_thinking: str | None = field(
    default_factory=lambda: _env_optional("LLM_THINKING")
)
```

`OPENAI_BASE_URL` 默认值同时改为 `https://api.openai.com/v1`。云端 key 应使用 `str | None`，
并像 `deepseek_configured()` 一样拒绝空值、`dummy`、`EMPTY` 和 `REPLACE_ME`；本地 SGLang/vLLM
则仍允许这类协议占位值。

### 0.9.3：建立独立 generation schema

在 `src/schemas/llm_config.py` 中保持 `LLMRunConfig` 只含 provider、base URL 和 model，另外定义：

```python
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.settings import ThinkingLevel


class AgentGenerationConfig(BaseModel):
    """Describe how a model should generate for one Agent run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    thinking: ThinkingLevel | None = None
```

直接复用 Pydantic AI 的 `ThinkingLevel`，可以跟随当前锁定版本对 `bool`、`minimal` 到 `xhigh`
等值的定义，不需要在项目内复制一份枚举。

### 0.9.4：新建 `src/ai/model_settings.py`

```python
"""Generation-policy boundary for Pydantic AI model runs."""

from __future__ import annotations

from pydantic_ai.settings import ModelSettings, merge_model_settings

from src.config import Settings, get_settings
from src.schemas.llm_config import AgentGenerationConfig


def build_model_settings(
    config: AgentGenerationConfig,
) -> ModelSettings | None:
    result: ModelSettings = {}
    if config.temperature is not None:
        result["temperature"] = config.temperature
    if config.max_tokens is not None:
        result["max_tokens"] = config.max_tokens
    if config.timeout_seconds is not None:
        result["timeout"] = config.timeout_seconds
    if config.thinking is not None:
        result["thinking"] = config.thinking
    return result or None


def application_generation_config(
    settings: Settings | None = None,
) -> AgentGenerationConfig:
    active = settings or get_settings()
    return AgentGenerationConfig(
        temperature=active.llm_temperature,
        max_tokens=active.llm_max_tokens,
        timeout_seconds=active.llm_timeout_seconds,
        thinking=active.llm_thinking,
    )


def resolve_model_settings(
    *,
    settings: Settings | None = None,
    agent_defaults: AgentGenerationConfig | None = None,
    run_override: AgentGenerationConfig | None = None,
) -> ModelSettings | None:
    resolved = build_model_settings(
        application_generation_config(settings)
    )
    if agent_defaults is not None:
        resolved = merge_model_settings(
            resolved, build_model_settings(agent_defaults)
        )
    if run_override is not None:
        resolved = merge_model_settings(
            resolved, build_model_settings(run_override)
        )
    return resolved
```

`is not None` 是这段代码的关键：`temperature=0` 是有效 override，不能因为 falsy 而丢失。
`merge_model_settings()` 的合并顺序则实现了本章定义的四级优先级。

### 0.9.5：让 factory 回归 deployment policy

从 `_OpenAICompatibleConfig` 删除 `timeout_s`。SGLang 和 vLLM 继续使用 `OpenAIProvider` 和保守
profile；OpenAI 使用官方默认 URL；DeepSeek 只使用官方 provider：

```python
from pydantic_ai.providers.deepseek import DeepSeekProvider

OFFICIAL_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def build_agent_model(config: AgentModelConfig) -> Model:
    if isinstance(config, DeepSeekModelConfig):
        return OpenAIChatModel(
            config.model,
            provider=DeepSeekProvider(
                api_key=config.api_key.get_secret_value()
            ),
        )

    provider = OpenAIProvider(
        base_url=(
            None
            if isinstance(config, OpenAIModelConfig)
            and config.base_url == OFFICIAL_OPENAI_BASE_URL
            else config.base_url
        ),
        api_key=config.api_key.get_secret_value(),
    )
    if isinstance(config, (SGLangModelConfig, VLLMModelConfig)):
        return OpenAIChatModel(
            config.model,
            provider=provider,
            profile=_local_compatible_profile(config),
        )
    return OpenAIChatModel(config.model, provider=provider)
```

由于没有直接 import `openai.AsyncOpenAI`，本章不需要新增 `openai` 直接依赖。
自定义 DeepSeek URL 在 `resolve_agent_model_config()` 阶段被拒绝。

### 0.9.6：在 run 边界汇合

`PydanticAIRuntimeAdapter` 不再接收单独的 `temperature`/`max_tokens`，而是接收：

```python
from pydantic_ai.settings import ModelSettings

# __init__ and from_agent
model_settings: ModelSettings | None = None

self.model_settings = model_settings
```

在实际 run 时传入：

```python
result = await self.agent.run(
    goal,
    deps=self.deps,
    message_history=message_history,
    model_settings=self.model_settings,
    usage_limits=limits,
    run_id=self.deps.run_id,
    conversation_id=conversation_id,
)
```

先只选 `src/pipelines/llm_tool_research.py` 作为第一条端到端路径：

```python
generation_settings = resolve_model_settings(settings=settings)

return PydanticAIRuntimeAdapter(
    model=agent_model,
    deps=deps,
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    model_settings=generation_settings,
)
```

这里依然单独传入 `usage_limits`。`max_tokens` 限制一次生成的输出，`UsageLimits` 约束整个
Agent run 能使用多少次请求、工具调用或 token，两者不可互换。

### 0.9.7：最小离线验收

新建 `tests/ai/test_model_settings.py`，至少覆盖：

```python
def test_zero_temperature_is_preserved() -> None:
    result = build_model_settings(
        AgentGenerationConfig(temperature=0)
    )
    assert result == {"temperature": 0}


def test_resolution_precedence() -> None:
    result = resolve_model_settings(
        settings=Settings(
            llm_temperature=0.1,
            llm_max_tokens=2000,
            llm_timeout_seconds=60,
        ),
        agent_defaults=AgentGenerationConfig(
            temperature=0.2,
            max_tokens=1000,
        ),
        run_override=AgentGenerationConfig(
            temperature=0,
            thinking="high",
        ),
    )
    assert result == {
        "temperature": 0,
        "max_tokens": 1000,
        "timeout": 60,
        "thinking": "high",
    }
```

factory 测试断言 OpenAI 默认 URL、云端占位 key 在网络前失败、`SecretStr` 不出现在
`repr(config)`、官方 DeepSeek 使用专用 profile，以及自定义 DeepSeek endpoint 被显式拒绝。

## 0.10：实施结果与后续顺序

本章已按以下顺序落地：

1. 增加 generation config、映射和合并测试；
2. 让 `llm_tool_research` 路径显式接收并传递 `ModelSettings`；
3. 证明 timeout 真正到达 Pydantic AI run boundary；
4. 修正 OpenAI 默认 endpoint 与占位 key 校验；
5. 将 DeepSeek 收紧为官方 provider，拒绝未定义的代理语义；
6. 删除未使用的 `llm_model` 和 provider-specific generation 字段。

后续应在 Chapter 1 中为具体 typed Agent 添加 task-specific defaults，再根据实际需求决定是否
扩展 API generation override 和分项 live capability probes。

## 0.11：验收

当前基线测试：

```bash
uv run python -m pytest -q \
  tests/ai/test_model_settings.py \
  tests/ai/test_model_factory.py \
  tests/ai/test_live_acceptance.py \
  tests/test_config.py
```

实施职责分离后还应增加：

```text
generation settings validation
None/zero override semantics
Agent default vs run override precedence
timeout reaches ModelSettings or HTTP client
official DeepSeek provider/profile
custom DeepSeek endpoint rejection
official OpenAI endpoint default
OpenAI Chat vs Responses capability selection
removed config has no production reference
secret redaction for every provider path
```

有可用 provider 时再运行：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --base-url http://localhost:30000/v1 \
  --model qwen3.8-27b
```

- [x] factory 只决定 endpoint、provider、model class 和 profile。
- [x] generation semantics 由 `ModelSettings` 管理并支持 run override。
- [x] `max_tokens` 没有冒充 total token budget。
- [x] timeout 配置可以证明真正生效。
- [x] DeepSeek 官方 endpoint 和自定义 endpoint 拒绝策略明确。
- [x] `provider="openai"` 不再默认连接 SGLang。
- [x] 未使用配置已删除，仍在使用的默认 provider 没有误删。
- [x] 默认测试离线，live acceptance 显式运行且错误脱敏。

完成本章后，Chapter 1 再把 model、generation settings 与具体 typed Agent 任务组合起来。
