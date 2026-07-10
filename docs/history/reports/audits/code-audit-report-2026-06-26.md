# FinText-LLM 项目审计报告

审计日期：2026-06-26

验证结果：初次审计时 `uv run pytest -q` 通过，`710 passed, 7 skipped in 12.34s`。后续整改复查时测试已扩展到 `749 passed, 7 skipped`，并继续新增 run-store / LLM 日志脱敏覆盖。

## 1. 项目总体概览

项目当前主要定位是 **FinRisk Agent Studio / 金融风险情报工作流系统**，用于结合 SEC filings、网页证据、LLM、图推理和质量 guardrails，生成结构化金融风险分析报告。依据来自 `README.md`、`src/workflows/finrisk_workflow.py`、`src/api/main.py`。

核心模块包括：

- `src/workflows/`：FinRisk 主工作流编排。
- `src/workflows/steps/`：公司解析、filing 风险提取、市场证据、评分、图推理、报告生成。
- `src/api/`：FastAPI API。
- `src/schemas/`：Pydantic 数据契约。
- `src/evaluation/`：质量层、guardrails、claim grounding。
- `src/graph_reasoning/`：候选路径、路径评分、证据绑定、图洞察验证。
- `src/supply_chain/`：供应链探索和 Sankey payload。
- `src/tools/`、`src/browser/`、`src/data/`：搜索、浏览器、SEC/外部数据接入。

成熟度判断：初次审计为 **内部工具 / 高质量原型，尚非生产级项目**。后续整改后，API 鉴权、限流、SSRF guard、CI、镜像 pinning、SQLite run-store 可选后端和 LLM 日志脱敏均已落地；若不公网部署 API，可判断为 **内部工具 / 内部试点可用**。

## 2. 技术栈总结

- 语言：Python `>=3.12,<3.13`，见 `pyproject.toml`。
- 后端：FastAPI、Uvicorn，见 `pyproject.toml`。
- 数据建模：Pydantic v2 风格，核心 schemas 使用 `BaseModel`、`ConfigDict(extra="forbid")`。
- LLM：OpenAI-compatible client、DeepSeek、sglang/vLLM 配置，见 `src/config.py`。
- 图数据库：Neo4j driver，见 `src/graph/client.py`。
- 数据/抓取：SEC、requests、httpx、trafilatura、BeautifulSoup、Playwright、DuckDB、datasets。
- 搜索：DuckDuckGo、Tavily、Brave、SearxNG 等 provider。
- 测试：pytest、pytest-asyncio、pytest-cov，见 `pyproject.toml`。
- 构建/包管理：uv + `uv.lock`。
- 部署：`docker-compose.yml` 包含 sglang 和 Neo4j；整改后已新增 `.github/workflows/ci.yml`。未发现 Dockerfile、Kubernetes。
- 前端：README 和 API 注释提到 dashboard/frontend contract，但当前仓库未发现真实 `frontend/` 源码目录，仅有 `tests/frontend_contract/`。

## 3. 目录结构与模块划分

```text
/
├── src/api/              FastAPI 路由与运行状态存储
├── src/workflows/        FinRisk 工作流编排与步骤
├── src/supply_chain/     供应链探索、Sankey、递归扩展
├── src/schemas/          Pydantic 领域模型/API 契约
├── src/evaluation/       质量层、guardrails、指标
├── src/graph_reasoning/  图推理子系统
├── src/graph/            Neo4j 客户端、writer、queries
├── src/data/             SEC、XBRL、transcript、外部 provider
├── src/llm/              LLM 客户端
├── src/tools/            搜索、fetch、router
├── src/browser/          浏览器探索封装
├── tests/                单元/契约/集成测试
├── eval/                 golden cases 与评估入口
├── scripts/              demo 与工具脚本
└── docs/                 规格、路线图、实施计划
```

结构总体清晰，模块边界较好。主要问题是版本演进痕迹较重：`v15/v16/v17/v18` 多代概念并存；`README_CN.md` 仍描述较早的 Spark/Neo4j/sglang 系统和简化目录，与当前代码不一致。`main.py` 仍是占位式输出，不是实际入口。

## 4. 核心业务流程总结

### 流程一：FinRisk 工作流 API

- 入口：`POST /workflows/finrisk/run`，见 `src/api/workflows.py`。
- 核心函数：`start_workflow()`、`_run_and_store()`、`run_finrisk_workflow_v16()`、`run_finrisk_workflow()`。
- 步骤：CompanyResolver -> FilingRiskExtractor -> MarketExplorer -> EvidenceNormalizer -> RiskScorer -> LifecycleClassifier -> GraphReasoner -> ReportGenerator -> Evaluator。
- 输入：`FinRiskRequest`，包含 `ticker`、`analysis_goal`、`sources`、`demo_mode` 等。
- 输出：状态、trace、report、evaluation、graph、artifacts。
- 外部依赖：SEC、搜索 provider、LLM、可选 Neo4j。
- 异常：后台任务捕获异常并将 state 标记为 `failed`。

### 流程二：供应链探索 API

- 入口：`POST /supply-chain/explore`、`POST /supply-chain/expand`，见 `src/api/supply_chain.py`。
- 输入：`SupplyChainExploreRequest` / `SupplyChainExpandRequest`。
- 输出：`SankeyPayload`、status、warnings、fallback events。
- 特点：当前使用 `DEFAULT_STATE_STORE` 内存 dict，适合 demo。

### 流程三：CLI

- 入口：`uv run python -m src.workflows.finrisk_workflow ...`，见 `src/workflows/finrisk_workflow.py`。
- 输出：可选 JSON state 和 Markdown report。
- 备注：根目录 `main.py` 只是占位说明，不是实际业务入口。

## 5. 架构分析

架构模式：**模块化单体 + 分层工作流 + Agent/Workflow 架构 + 图推理子系统**。

```text
User / Client
    ↓
FastAPI API Layer
    ↓
Workflow Orchestrator
    ↓
Workflow Steps
    ↓
Data / Search / Browser / LLM / Graph Reasoning
    ↓
Pydantic State + Evaluation Guardrails
    ↓
Report / Graph Payload / API Response
```

优点：状态对象统一为 `FinRiskWorkflowState`；schemas 明确；质量层和图推理模块独立；测试覆盖广。

不足：API 层缺少生产级鉴权、持久化、限流和任务队列；v16 字段在 `FinRiskWorkflowState` 中大量使用 `Any/list`，依赖运行时校验和测试约束，长期维护会增加类型漂移风险，见 `src/schemas/finrisk.py`。

## 6. 数据模型与存储分析

核心模型：

- `FinRiskRequest`：工作流请求；校验 ticker、analysis_goal、sources，见 `src/schemas/finrisk.py`。
- `FinRiskWorkflowState`：主状态对象；承载 company、risks、evidence、scores、graph、report、evaluations，见 `src/schemas/finrisk.py`。
- `ExtractedRisk` / `NormalizedEvidence` / `RiskScore` / `RiskReport`：核心报告数据。
- `SupplyChainExploreRequest`、`SupplyChainNode`、`SupplyChainEdge`、`SankeyPayload`：供应链图和 Sankey 契约，见 `src/supply_chain/models.py`。
- Neo4j 图模型：通过 `Entity`、`Relation`、`Claim`、`Evidence` 写入，见 `src/graph/writer.py`。

未发现数据库迁移文件。持久化主要为 Neo4j 写入、缓存目录、fixture、内存 run store。API run 状态没有数据库表或 durable queue。

## 7. API 与接口分析

主要接口：

- `GET /`：服务元数据。
- `POST /workflows/finrisk/run`：启动 FinRisk run。
- `GET /workflows/health`：健康检查。
- `GET /workflows/{run_id}`：状态和 trace。
- `GET /workflows/{run_id}/report`：报告。
- `GET /workflows/{run_id}/trace`、`/graph`、`/evaluation`、`/artifacts`、`/llm_log`、`/chunks`、`/sections`、`/lifecycles`：观测与质量数据。
- `POST /supply-chain/explore`、`POST /supply-chain/expand`、`GET /supply-chain/{run_id}`、`GET /supply-chain/{run_id}/sankey`。

初次问题：未发现鉴权依赖、API key middleware、CORS 配置、权限控制。整改后：`src/api/main.py` 已为 workflow / supply-chain router 增加 `X-API-Key` 依赖，并加入进程内 rate limit。用户明确不计划公网部署 API，因此公网暴露风险降级；内部共享服务仍建议配置 `FINRISK_API_KEYS`。

## 8. 配置、环境变量与部署分析

主要配置来自 `src/config.py` 和 `.env.example`。

配置项包括：`SEC_USER_AGENT`、`SEC_RATE_LIMIT_PER_SECOND`、`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`DEEPSEEK_*`、`LLM_PROVIDER`、`NEO4J_*`、`CACHE_DIR`、`SEARCH_PROVIDER_ORDER`、`TAVILY_API_KEY`、`BRAVE_API_KEY`。

安全观察：

- `.env.example` 使用 `REPLACE_ME`、`EMPTY`、`dummy`，未发现真实 key。
- `docker-compose.yml` 已改为从 `NEO4J_USER` / `NEO4J_PASSWORD` 读取凭据。
- 已新增 `.github/workflows/ci.yml`。
- 未发现 Dockerfile。
- `docker-compose.yml` 已 pin 到 `lmsysorg/sglang:v0.4.10-cu130-runtime` 和 `neo4j:5.26.0`；见 `docs/docker-image-pinning.md`。

## 9. 安全性审查

| 风险 | 等级 | 位置 | 说明 | 建议 |
|---|---:|---|---|---|
| API 无鉴权 | 已缓解 | `src/api/*.py` | 已增加 `X-API-Key` 与进程内限流；不公网部署时风险进一步下降 | 内部共享服务仍配置 `FINRISK_API_KEYS` |
| 内存 run store | 部分缓解 | `src/api/run_store.py`, `src/api/store_factory.py` | 已支持 FinRisk 与 supply-chain SQLite 后端；默认仍为 memory 以保持 demo/test 轻量 | 需要保留历史 run 时设置 `RUN_STORE_BACKEND=sqlite` |
| SSRF 潜在风险 | 已缓解 | `src/tools/web_fetch.py`, `src/browser/wrapper.py` | 已新增 `src/security/url_guard.py`，阻止私网/loopback/link-local 等地址 | DNS rebinding 和浏览器 redirect 残余风险见 `docs/security/known-limitations.md` |
| 浏览器工具滥用 | 中 | `src/browser/wrapper.py` | 可导航任意 http(s)，适合内部工具，不适合公网暴露 | 加域名策略、沙箱、审计、超时与并发限制 |
| 默认 Neo4j 密码 | 已修复 | `docker-compose.yml` | 已改为环境变量 | 非本地环境必须设置真实 `.env` |
| LLM 日志泄露 | 已缓解 | `src/schemas/finrisk.py`, `src/security/redaction.py` | `LLMCall` 已对明显敏感模式脱敏，但不是合规级 DLP | 仍建议限制日志访问和保留周期 |
| Prompt injection / 工具越权 | 中 | `src/tools/`, `src/browser/`, `src/agents/` | 项目具备网页抓取和 LLM 工具调用能力，未看到统一工具权限策略 | 增加 tool policy、source trust、人工确认机制 |
| SQL 注入 | 低 | 未发现 SQL 数据库路径 | Neo4j 写入使用参数化属性，关系类型有映射/转换 | 保持参数化，审查动态 Cypher label/type |
| XSS/CSRF | 需确认 | 未发现前端源码 | 仅后端 API，未见 cookie auth | 前端引入后再评估 |

## 10. 代码质量与可维护性

总体质量较好。优点是模块划分清楚、schemas 严格、测试多、注释解释了演进背景。主要技术债：

- 多版本概念并存：`v15/v16/v17/v18` 命名贯穿 docs、API、state，影响新成员理解。优先级中。
- `FinRiskWorkflowState` v16 字段使用 `Any/list`：类型安全不足。优先级中。
- `README_CN.md` 初次审计时与当前代码明显不一致；后续已更新为英文 README 的结构对位中文版。
- `main.py` 占位入口可能误导：优先级低。
- API 与 workflow tightly coupled：API 直接创建后台 task、直接使用内存 store；后续生产化需要抽象任务队列和存储。优先级高。

## 11. 测试情况分析

测试情况强于多数原型项目：

- 发现 `100` 个 `test_*.py` 文件，`111` 个测试相关 Python 文件。
- 当前执行：`710 passed, 7 skipped`。
- 覆盖范围包括 agents、api、browser、data、evaluation、graph、graph_reasoning、llm、memory、pipelines、schemas、supply_chain、tools、workflows。
- 有 integration marker，见 `pyproject.toml`。

缺口：

- 已新增 CI 自动运行 changed-files ruff、全仓 advisory ruff 和非 integration pytest。
- 已补鉴权、限流、SQLite run-store、SSRF guard 测试。
- 后续仍可补多进程部署和真实队列/Redis 场景测试。
- 多进程 API 状态一致性测试缺失。

## 12. 性能与可扩展性分析

主要性能风险：

- LLM chunked extraction 可能多次调用模型，成本和延迟随 filing 长度增长。
- API 后台任务使用 `asyncio.create_task`，没有队列、并发控制、重试策略或 worker 隔离。
- `SearchRouter` 有缓存，TTL 默认 3600 秒，利于减少重复请求，但缓存失效策略较简单。
- `web_fetch` 限制内容 100KB，降低内存风险。
- 内存 store 随 run 增长无清理机制，长期运行可能内存膨胀。

## 13. 依赖与供应链风险

未进行在线漏洞库查询，仅基于代码仓库静态信息判断。

风险点：

- `docker-compose.yml` 使用 `latest` 镜像，构建不可复现。
- 依赖版本多为下限约束，如 `fastapi>=0.132.0`，但有 `uv.lock` 锁定解析结果。
- 依赖面较宽：LLM、浏览器、Spark、Neo4j、scraping、ML、search providers，供应链审计成本较高。
- 未发现 Dependabot/Renovate/audit CI 配置。

## 14. 可运行性与工程化

可运行性评分：**7/10**。

优点：README 有 `uv sync`、`uv run pytest -q`，测试能直接通过；`.env.example` 完整；docker-compose 提供本地 sglang/Neo4j。

阻碍：无 CI/CD；无 Dockerfile；生产启动、worker、持久化、secret 管理不完整；中文 README 过期；GPU compose 对普通机器门槛高。

## 15. 风险清单

| 编号 | 风险类型 | 等级 | 所在位置 | 摘要 | 建议 | 优先级 |
|---|---|---:|---|---|---|---|
| R1 | 安全 | 已缓解 | `src/api/` | 已增加认证、限流 | 内部服务配置 key | 已完成 |
| R2 | 架构/运行 | 部分缓解 | `src/api/run_store.py` | SQLite 后端已支持 FinRisk 与 supply-chain；默认仍 memory | 需要历史状态时启用 SQLite | P1 |
| R3 | 安全 | 已缓解 | `src/tools/web_fetch.py` | 私网 IP 拦截已实现 | 关注残余 DNS/redirect 风险 | 已完成 |
| R4 | 部署 | 已修复 | `docker-compose.yml` | 默认密码已移除 | 使用真实 `.env` | 已完成 |
| R5 | 工程 | 已修复 | `.github/workflows/ci.yml` | CI 已新增 | 持续维护 | 已完成 |
| R6 | 文档 | 已修复 | `README_CN.md` | 已更新 | 持续同步 | 已完成 |
| R7 | 类型 | 中 | `FinRiskWorkflowState` | 多个 `Any/list` v16 字段 | 收敛类型模型 | P2 |
| R8 | 供应链 | 中 | `docker-compose.yml` | latest 镜像未 pin | pin tag/digest | P2 |

## 16. 优先级整改建议

### P0：必须立即处理

- API 鉴权与限流：涉及 `src/api/main.py`、`src/api/workflows.py`、`src/api/supply_chain.py`。收益是避免公网滥用高成本任务。
- 持久化 run store：涉及 `src/api/run_store.py`、`src/api/supply_chain.py`。收益是支持重启恢复、多进程部署。

### P1：短期应处理

- SSRF 防护：涉及 `src/tools/web_fetch.py`、`src/browser/wrapper.py`。收益是降低内部网络探测风险。
- CI：新增 GitHub Actions 或其他 CI，运行 `uv run pytest -q` 和 `uv run ruff check .`。
- 更新 README_CN 和运行说明：减少交接误解。

### P2：中期优化

- 收敛 v16/v17/v18 状态字段类型。
- 引入任务队列，如 Celery/RQ/Arq 或 FastAPI worker 模式。
- pin Docker 镜像版本/digest。

### P3：长期规划

- 前后端契约正式化。
- 将 demo、实验、生产路径拆分为明确 profile。
- 建立依赖漏洞扫描和 secret scanning。

## 17. 项目评分

| 维度 | 分数 | 理由 |
|---|---:|---|
| 业务清晰度 | 8 | README 和 workflow 目标明确 |
| 架构合理性 | 7 | 模块化清楚，但生产边界不足 |
| 代码可维护性 | 7 | schemas/tests 强，多版本概念增加理解成本 |
| 安全性 | 5 | 无真实 key 泄露，但 API/SSRF/鉴权不足 |
| 测试覆盖 | 8 | 710 tests 通过，覆盖面广 |
| 部署成熟度 | 4 | compose 仅本地服务，无 CI/CD/Dockerfile |
| 可扩展性 | 6 | 工作流可扩展，运行时任务/存储不可扩展 |
| 文档完整度 | 6 | 英文 README 好，中文 README 过期 |
| 工程规范 | 7 | uv、ruff、pytest 到位，CI 缺失 |
| 整体生产可用性 | 5 | 适合内部 demo/研究，不建议直接公网生产 |

总体评分：**6.3/10**。

建议：**继续投入，适合接手和内部试点；不建议不经整改直接上线公网生产**。最大优势是 schema、workflow、guardrail 和测试基础扎实。最大风险是 API 生产安全与运行时持久化不足。最优先三项：API 鉴权、持久化 run store、SSRF/工具权限控制。

## 18. 面向非技术人员的摘要

这个项目是一个用 AI 帮助分析公司金融风险的系统，可以读取 SEC 文件、搜索市场证据、生成风险报告，并检查报告是否有证据支撑。

当前代码质量不错，测试很多，说明团队已经做了较认真工程化。但它更像内部演示和试点系统，还没有达到可以直接对外上线的成熟度。

最大的风险是：如果公开部署，别人可能无需权限就启动昂贵的 AI 分析任务；运行状态也存在重启丢失的问题。建议继续投入，但先补安全、持久化和部署流程。

## 19. 面向技术团队的摘要

项目是模块化单体，核心是 Pydantic state-driven workflow。`src/workflows` 编排业务路径，`src/evaluation` 做质量层，`src/graph_reasoning` 做图路径解释，`src/api` 暴露 demo/productization API。

主要技术债集中在：无鉴权、无 durable store、无 CI/CD、文档漂移、v16/v17/v18 状态字段类型弱化。建议路线：先补 API 安全和存储，再补 CI 与 SSRF 防护，之后再清理版本命名和类型边界。

## 20. 人工复核清单

- 是否计划公网部署 API？如果是，必须确认鉴权、限流和网络隔离方案。
- 是否需要保存历史 run/report？如果需要，确认数据库/对象存储方案。
- Neo4j 是否为生产依赖，还是仅 demo/图实验？
- README_CN 是否仍面向用户？如是，需要按当前 FinRisk Agent Studio 更新。
- 前端源码是否在另一个仓库？当前仓库只看到 contract tests。
- 是否需要合规审查 LLM prompt/response 日志中的潜在敏感信息。
- 是否需要在线依赖漏洞扫描和容器镜像扫描。
