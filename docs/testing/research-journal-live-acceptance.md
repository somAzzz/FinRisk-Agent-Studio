# Research Journal 本地 LLM 真实验收

这套流程用真实 Chromium、隔离的 FastAPI/Vite、真实 SEC 数据和本地 OpenAI-compatible LLM 完成 Research Journal 全链路验收。每次运行创建独立 SQLite 数据库，不会写入个人研究库；下一次通常只需复制并修改一份 JSON 场景。

## 前置条件

- 已执行 `uv sync`、`cd frontend && npm install`，并安装 Playwright Chromium。
- 本地 LLM 的 `/v1/models` 可访问；配置中的 model ID 必须与服务返回值完全一致。
- SEC、transcript、web 和 Neo4j 使用项目现有环境配置。外部来源不可用可形成 partial snapshot，但本地 LLM 调用必须真实成功。
- 配置中的 API/Vite 端口未被占用。

## 直接运行

```bash
uv run python scripts/research_journal_live_acceptance.py
```

默认场景为 `config/acceptance/research_journal_live.json`。输出保存在：

```text
artifacts/research-journal-live/<scenario>-<UTC timestamp>/
├── report.json
├── browser-report.json
├── api.log
├── frontend.log
├── research-journal.sqlite
├── research-snapshots.sqlite
└── screenshots/
```

`report.json` 是最终判定依据；它同时验证浏览器行为、持久化状态、workflow 终态和成功的本地 LLM 调用。失败时仍保留报告、日志和 failure screenshot。

## 新场景只改什么

复制默认 JSON，并修改：

- `scenario_id` 和两个隔离端口；
- `primary` 的 ticker、两个财年、thesis 和分析目标；
- `peer` 的 ticker 和组名；
- 历史 expectation。`observed_at`/`as_of` 必须早于相应实际财报公开时间；
- 显式估值假设；
- `llm.provider`、`base_url`、`model`。

运行新文件：

```bash
uv run python scripts/research_journal_live_acceptance.py \
  --config config/acceptance/my_company.json
```

不要把 API key 或云端 LLM 密钥写入场景。场景中的 `api_key` 只用于本机隔离服务；云端密钥仍通过环境变量传入。

## 覆盖范围与通过条件

浏览器依次完成：active thesis、Watchlist、两期主公司快照、FinRisk + snapshot、本地 LLM 参数检查、变化确认、Expectation–Actual、peer snapshot、Scenario/Sensitivity/Multiple/DCF、Peer Analysis、Post-earnings review，以及桌面/移动端布局检查。

最终 API 复核要求：

- 主公司至少 2 个快照、peer 至少 1 个；
- thesis、Watchlist、peer group 和 confirmed review 已落库；
- valuation history 同时包含四种类型；
- workflow 为 `completed` 或 `needs_review`；
- workflow LLM log 至少有一次匹配配置 provider、无错误且响应非空的调用；
- 浏览器无同源 HTTP 4xx/5xx、console error 或移动端横向溢出。

`needs_review` 是质量门禁终态，可以通过；fixture/demo/cached workflow 不能通过。

## 常用诊断选项

```bash
# 显示真实浏览器
uv run python scripts/research_journal_live_acceptance.py --headed

# 指定输出目录
uv run python scripts/research_journal_live_acceptance.py --output-dir /tmp/journal-run

# 调试时保留隔离服务
uv run python scripts/research_journal_live_acceptance.py --keep-services
```

`--reuse-services` 只用于已经按场景端口、API key 和隔离数据库启动服务的调试环境；常规验收不要使用。

