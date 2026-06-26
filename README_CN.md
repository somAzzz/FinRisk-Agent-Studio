# FinText-LLM

> **本中文版为英文 `README.md` 的结构对位文档。** 章节顺序、代码块、配置项与英文版一致;终端命令、代码、配置 key、模型名、API 路径保持英文不译,术语附首次出现时的中文括注。**当英文版与本中文版不一致时,以英文版为准。**

FinText-LLM 正在演进为 **FinRisk Agent Studio** —— 一个 AI-native 的金融风险情报工作流系统,融合 SEC filings、网络证据、本地或 API LLM、结构化输出、图推理和运行时质量 guardrails。

项目目标不是"和 filings 聊聊天"的演示,而是一套金融研究的工作流:

```text
Company Resolver(公司解析)
→ Filing Risk Extraction(财报风险提取)
→ Market Evidence Collection(市场证据收集)
→ Evidence Normalization(证据归一化)
→ Risk Scoring(风险打分)
→ Graph Reasoning(图推理)
→ Structured Report Generation(结构化报告生成)
→ Quality Layer / Human Review Gate(质量层 / 人工复核关)
```

## Current Direction(当前方向)

最新 roadmap 把项目聚焦在两个核心理念上:

1. **Quality Layer 贯穿每一步**
   评估与 guardrail 不只在报告生成后才跑。每个工作流步骤都应有 pre-step 与 post-step 校验,包括:schema 检查、证据覆盖、claim 溯源、来源质量、金融安全、图路径校验、fallback 跟踪。

2. **Graph Reasoning 作为子系统**
   图推理不是"把整张图丢给 LLM"。目标设计是:

```text
Graph Context Builder(图上下文构建)
→ Candidate Path Retriever(候选路径检索)
→ Path Scorer(路径打分)
→ Evidence Binder(证据绑定)
→ LLM / Template Path Interpreter(LLM/模板路径解读)
→ Graph Insight Validator(图洞察校验)
→ Evidence Graph Visualization(证据图可视化)
```

LLM 解释"已校验的路径"并生成研究假设,不发明图路径、不捏造事实、不给买卖建议。

## What This Project Demonstrates(本项目展示什么)

- Pydantic 优先的 agent workflow 设计
- 本地 LLM 与 OpenAI-兼容 API provider 支持
- SEC EDGAR filings 分析
- 定向市场证据收集
- 证据支撑的风险提取
- 确定性风险打分
- Claim ↔ evidence 溯源
- 图路径检索与排序
- 运行时 guardrail 与人工复核关
- 用于稳定演示的缓存 demo 模式
- FastAPI 与 dashboard 导向的产品化

## Planned Demo: FinRisk Agent Studio(规划中的演示)

示例用户请求:

```text
Company: Apple
Ticker: AAPL
Analysis Goal: 识别近期变化的宏观、政策与供应链风险。
Time Horizon: 未来 6-12 个月
```

预期输出:

- Top risks 及其严重度、打分拆解
- Filing 证据与近期市场证据
- Claim ↔ evidence 矩阵
- 来源质量警告
- 供应链 / 政策图路径
- 二阶风险洞察
- 结构化风险情报报告
- Guardrail 发现与人工复核状态
- 证据图可视化

## Existing Foundation(已有基础)

仓库已经包含以下基础模块:

- EDGAR 数据加载
- SEC filings 访问与章节解析
- Hugging Face EDGAR corpus 加载
- SGLang / OpenAI-兼容的结构化 LLM 客户端
- 浏览器探索
- 搜索路由与缓存
- 风险、情绪、机会与报告 agent
- Neo4j 图写入 / 查询组件
- 离线 demo fixtures 与测试
- Roadmap 与实施 spec

## Roadmap Documents(路线图文档)

从下面开始读:

```text
docs/implementation-plan/00-overview.md
```

最重要的当前规划:

```text
docs/implementation-plan/15-finrisk-agent-studio-workflow-roadmap.md
docs/implementation-plan/16-quality-layer-and-graph-reasoning-roadmap.md
```

Step 15 合并 spec:

```text
docs/specs/v15-finrisk-agent-studio/15-finrisk-agent-studio-combined-spec.md
```

Step 16 详细 spec:

```text
docs/specs/v16-quality-graph/00-index.md
docs/specs/v16-quality-graph/01-quality-layer-runtime.md
docs/specs/v16-quality-graph/02-claim-grounding-and-source-quality.md
docs/specs/v16-quality-graph/03-graph-reasoning-subsystem.md
docs/specs/v16-quality-graph/04-structured-report-and-risk-scoring.md
docs/specs/v16-quality-graph/05-api-and-frontend-quality-graph.md
docs/specs/v16-quality-graph/06-v16-demo-acceptance.md
```

## Target Architecture(目标架构)

```text
src/
├── agents/
├── api/
├── browser/
├── data/
├── evaluation/
│   ├── engine.py
│   ├── models.py
│   ├── validators/
│   └── metrics/
├── graph/
├── graph_reasoning/
├── llm/
├── reports/
├── schemas/
├── tools/
└── workflows/
    ├── finrisk_workflow.py
    ├── state.py
    └── steps/

frontend/
eval/
docs/
tests/
```

## Workflow Quality Layer(工作流质量层)

V16 plan 引入运行时质量层:

```text
Layer 1: Schema & Contract Guardrails(schema 与契约)
Layer 2: Evidence & Grounding Guardrails(证据与溯源)
Layer 3: Domain & Financial Safety Guardrails(领域与金融安全)
Layer 4: Workflow Quality & Regression Evaluation(工作流质量与回归评估)
```

检查项示例:

- Pydantic schema 合法
- 必填字段存在
- risk / evidence / claim 的 ID 引用合法
- 每条 top risk 都有证据
- 每条 claim 都有支撑的 evidence ID
- 来源质量与来源多样性
- 不出现直接的买卖建议
- 图路径在图中存在
- 图边要么有证据要么标记为 hypothesis
- fallback 事件被记录

## Graph Reasoning(图推理)

目标图流:

```text
Company + Risks + Evidence
→ Graph Query Context
→ Candidate Graph Paths
→ Path Score Breakdown
→ Evidence Binding
→ Path Interpretation
→ Graph Insight Validation
→ Evidence Graph Payload
```

图路径示例:

```text
Apple
→ depends_on
TSMC
→ located_in
Taiwan
→ exposed_to
Geopolitical Risk
```

洞察可以成为 **research theme** 或 **hypothesis**,但不是金融建议。

## Quick Start(快速开始)

安装依赖:

```bash
uv sync
```

跑测试:

```bash
uv run pytest -q
```

跑现有的离线公司分析 demo:

```bash
uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

规划的 FinRisk workflow CLI 入口:

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## Optional Local LLM Setup(可选本地 LLM 配置)

项目可用 SGLang 跑本地 LLM:

```bash
docker compose up -d
```

规划的 provider 配置:

```text
LLM_PROVIDER=sglang
LLM_PROVIDER=openai
LLM_PROVIDER=deepseek
LLM_PROVIDER=gemini
LLM_PROVIDER=claude
LLM_BASE_URL=http://localhost:30000/v1
LLM_MODEL=Qwen/Qwen3.5-35B-A3B
```

Demo 模式不应要求 GPU、API key、Neo4j、浏览器自动化或实时网络。

## LLM Providers(LLM provider)

LLM 层对所有 provider 保持 OpenAI-兼容 —— 每个 provider 变的只有 `base_url` 与 API key。

| Provider   | `LLM_PROVIDER` | `*_BASE_URL`              | Auth env var        | Default model        |
|------------|----------------|---------------------------|---------------------|----------------------|
| SGLang     | `sglang`       | `http://localhost:30000/v1` | `SGLANG_API_KEY`    | `Qwen/Qwen3.5-35B-A3B` |
| vLLM       | `vllm`         | `http://localhost:8000/v1`   | `VLLM_API_KEY`      | `Qwen/Qwen3.5-35B-A3B` |
| OpenAI     | `openai`       | `https://api.openai.com/v1`  | `OPENAI_API_KEY`    | `gpt-4o-mini`        |
| DeepSeek   | `deepseek`     | `https://api.deepseek.com`   | `DEEPSEEK_API_KEY`  | `deepseek-chat`      |
| Gemini     | `gemini`       | (OpenAI-compat shim)         | `GEMINI_API_KEY`    | `gemini-1.5-flash`   |
| Claude     | `claude`       | (Anthropic SDK)              | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet`  |

### DeepSeek quickstart(DeepSeek 快速上手)

DeepSeek 公开 API 兼容 OpenAI([文档](https://api-docs.deepseek.com)),所以直接用标准 `openai` Python SDK。

1. 到 <https://platform.deepseek.com> 申请 key。
2. 复制 `.env.example` 为 `.env`,填入 `DEEPSEEK_API_KEY`:

   ```text
   LLM_PROVIDER=deepseek
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   DEEPSEEK_MODEL=deepseek-chat
   DEEPSEEK_API_KEY=sk-...
   ```

3. 在代码里使用 client:

   ```python
   from src.llm import build_client_from_settings

   client = build_client_from_settings()
   if client.configured:
       text = client.complete("Summarise today's Apple 10-K risk factors.")
   ```

4. 或者调用结构化风险提取器:

   ```python
   from src.llm.deepseek_client import DeepSeekClient

   client = DeepSeekClient()
   result = client.extract_risks(
       section_1a, company_name="Apple", year=2024
   )
   ```

当 `DEEPSEEK_API_KEY` 缺失或仍是占位符时,client 抛 `DeepSeekNotConfigured`,demo / CI 跑不会误调真实 API。`deepseek-reasoner` 是 chain-of-thought 模型;通过 `DEEPSEEK_MODEL=deepseek-reasoner` 切换(注意 `deepseek-chat` 与 `deepseek-reasoner` 都计划在 2026-07-24 弃用,长期模型是 `deepseek-v4-flash` 与 `deepseek-v4-pro`)。

## Browser Exploration(浏览器探索)

浏览器探索作为**可选**证据获取路径,**不应**是唯一 demo 路径。

证据获取优先级:

```text
1. Cached evidence(缓存证据)
2. SearchRouter / structured search(结构化搜索)
3. Browser exploration(浏览器探索)
```

`SearchRouter` 支持可配置的 provider 优先级。Tavily 可作为 FinRisk workflow、市场探索、产品供应链发现的首个实时 web 搜索 provider:

```bash
export TAVILY_API_KEY=tvly-...
export SEARCH_PROVIDER_ORDER=tavily,duckduckgo
```

Brave Search API 接受任一 key 变量名:

```bash
export BRAVE_API_KEY=...
# or
export BRAVE_SEARCH_API_KEY=...
export SEARCH_PROVIDER_ORDER=brave,duckduckgo
```

支持的 provider 名称:

```text
duckduckgo
brave
tavily
searxng   # 透明 fallback —— 只在前面的 provider 都失败后启用
```

`TAVILY_API_KEY` 缺失时 Tavily 自动跳过,router 退到下一个配置的 provider。SearXNG 通过 `SEARXNG_BASE_URL`(如 `http://localhost:8080`)配置,对 LLM 不可见 —— 只在更高优先级 provider 用尽 retry 预算后激活。

可选安装:

```bash
cargo install agent-browser
agent-browser install
```

## Planned API(规划中的 API)

最小 API:

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
```

V16 API 扩展:

```text
GET /workflows/{run_id}/trace
GET /workflows/{run_id}/graph
GET /workflows/{run_id}/evaluation
GET /workflows/{run_id}/artifacts
```

规划的服务启动命令:

```bash
uvicorn src.api.main:app --reload
```

## Planned Dashboard(规划中的 Dashboard)

Dashboard 应是 workflow 产品 UI,不是 chat 界面。

Tab:

```text
Launcher
Timeline
Risk Report
Evidence Graph
Evaluation
```

Evaluation tab 应展示:

- 评估概览
- 步骤质量时间线
- Claim ↔ evidence 矩阵
- 风险打分拆解
- Guardrail 发现抽屉
- 来源质量警告
- 图路径校验状态

## Development Priorities(开发优先级)

建议顺序:

1. 稳定现有代码,提交已有文档
2. 实现 workflow schemas 与 state
3. 实现缓存版 MVP workflow
4. 加入运行时 Quality Layer
5. 加入 claim grounding 与 source quality
6. 加入图推理子系统与 fixture 图
7. 生成结构化报告模型与 markdown 渲染
8. 暴露 API endpoints
9. 构建 dashboard tabs
10. 用真实的 SEC / web / transcript / Neo4j 集成替换 fixture

## Non-Goals(非目标)

首个 demo 不试图解决所有问题:

- 不提供直接投资建议
- 不给买卖推荐
- 不强制要求浏览器成功
- 不要求 GPU
- 不要求 API key
- 不要求 live Neo4j
- 不做通用 chatbot UI

## License(许可)

本项目包含 Yahoo Finance 的数据,按 ODC-BY 授权。
