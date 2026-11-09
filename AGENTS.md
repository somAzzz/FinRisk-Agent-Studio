# FinRisk Agent Studio 开发约定

本项目是以证据为基础的金融研究工作台。修改行为前，先从受影响的用户入口跟踪到工作流、数据模型和对应测试。[中文 README](README_CN.md) 说明如何运行项目，[系统架构](docs/ARCHITECTURE.md) 和 [v0.1 规格](docs/specs/v0.1.md) 说明设计与验收要求。仅在用户明确调用 `$sol-sglang-build` 时启用全局约定中的委派流程。

## 按任务定位代码

| 任务 | 从这里开始 |
| --- | --- |
| 金融风险分析与报告 | 从 [工作流](src/workflows/) 跟踪证据归一化、风险评分和报告生成。涉及结论或引用时，同时检查[数据模型](src/schemas/)和[质量校验](src/evaluation/)。 |
| Agent 与工具调用 | 先读 [Pydantic AI 运行时决策](docs/ADR_PYDANTIC_AI_RUNTIME.md)。模型创建统一经过 [model_factory](src/ai/model_factory.py)，工具输入输出与搜索实现在 [src/tools](src/tools/)。预算、审批、运行记录和业务降级由项目代码控制。 |
| 图推理与供应链 | [图推理](src/graph_reasoning/)负责检索路径、绑定证据与校验解释。[供应链工作流](src/supply_chain/)负责产品分解、供应商发现和图投影。区分候选关系与已有证据支持的关系。 |
| 公司研究与年报 | [研究模块](src/research/)处理时点快照、同行比较、估值与监控。[年报模块](src/annual_reports/)处理披露文档、分部与产品证据。财务事实的修改应保留来源、报告期间、币种、单位和修订口径。 |
| API 与界面 | 从 [FastAPI 路由](src/api/)和[前端 API 客户端](frontend/src/api.ts)核对请求、响应和运行状态。修改共享展示逻辑时，同时考虑本地后端和 GitHub Pages 的静态演示数据。 |

## 证据与行为修复

- 从失败运行的输入、工具结果、trace 和质量校验结果定位问题。评分或财务计算错误应修复对应的确定性逻辑；引用错误应追查来源、证据绑定及校验过程。
- 模型可以抽取披露内容、解释有证据的路径、提出研究假设。报告应让读者区分原始披露、计算结果和推断，并保留可回查的引用。维持金融安全检查与人工复核状态。
- 缺失数值、显式零、未找到证据和上游请求失败应保留各自语义。使用缓存、fixture 或确定性降级时，应在结果或运行记录中保留实际来源。模型提供方失败时，遵循运行时决策，禁止静默切换提供方。
- 在负责该行为的层编写可复现的回归测试，先复现失败，再验证修复。涉及预算、审批或证据校验时，构造超限调用、未获批准的操作或无效引用，检查实际执行结果。

## 按改动范围验证

以 [CI 配置](.github/workflows/ci.yml) 为准。以下 Python 命令在仓库根目录执行，前端命令在 `frontend/` 执行。

- **Python 3.12**：用 `uv sync --frozen` 安装锁定依赖。先对改动的 Python 文件运行 `uv run ruff check <文件路径>`，再用 `uv run pytest <测试路径> -q` 运行相关用例。与 CI 对齐的非集成测试命令是 `uv run pytest -m "not integration" -q --maxfail=1`。
- **前端**：使用 Node.js 22 和 `npm ci` 安装依赖，运行 `npm test` 和 `npm run build`。依赖变更还应核对 CI 使用的 `npm audit --audit-level=moderate`。
- **外部服务**：真实数据验收见[验收指南](docs/testing/real-data-acceptance.md)。模型提供方或运行时变更另见[模型服务验收指南](docs/guides/llm-provider-validation.md)。分别记录离线结果、真实服务结果及未执行项。
- **纯文档**：核对路径、命令和实际差异。更新项目说明时，以 [英文 README](README.md) 为主，并同步中文版对应内容；其他文档按[文档索引](docs/README.md)维护。

## 工作区与提交

保留已有暂存和未暂存改动。注释优先解释调用方需要知道的金融口径、约束和副作用。仅在用户要求提交时创建 commit；提交前检查完整暂存差异，保持单一主题，使用 Conventional Commits 祈使句标题，整行不超过 72 个字符。推送需用户明确授权。
