# Runtime Cutover Playbook

> 状态：历史可重演。本 playbook 用于学习从旧 tool loop 迁移到 Pydantic AI，
> 不是当前 `main` 的 backlog。

## 学习结果

完成后应能用证据说明：

1. 新 model/deps/tool/output 边界不依赖旧 runtime；
2. 所有生产调用方已迁移；
3. 旧 runtime、generic JSON repair 和 fallback 分支已删除；
4. 确定性领域合同、评分、证据和审核边界没有被 Agent 吞掉；
5. 测试、eval、source gate 和 live acceptance 共同支持 cutover 结论。

## Phase 0：隔离历史练习

使用历史基线 `023c02f91be43ecf6428d12e5dac3272569a62b3`。开始前记录：

- 基线 commit 和依赖锁文件；
- 当前全量测试结果；
- 会发起模型调用的 API、CLI、workflow 和 background jobs；
- provider、凭据、工具 schema、重试、预算、trace 和 fallback 的所有者。

学习分支只用于练习。不要把历史 lockfile 或旧 runtime 提交回当前 `main`。

## Phase 1：先建立新边界

对照当前 [Chapter 6](../../06-toolsets.md) 的职责，先让以下部分在离线测试中独立成立：

| 边界 | 必须证明的性质 |
| --- | --- |
| Model factory | provider/model/base URL/API key 只在 composition boundary 解析 |
| Run-scoped deps | identity、permissions、services、budget 不跨 run 泄漏 |
| Typed tools | Python 签名是 schema 真相源，失败语义稳定 |
| Tool authorization | 可见性过滤和执行时权限复核都存在 |
| Usage/budget | request、tool call、deadline 等预算有明确所有者 |
| Typed outputs | 每个模型边界返回专用 model，不做 generic JSON repair |

此阶段允许旧 runtime 继续服务尚未迁移的调用方，但新边界不能调用旧 `complete()`、
`parse()` 或手写 tool loop。

### Gate A

- model/deps/tool/output 单元测试默认离线；
- 未授权工具既不向模型暴露，也无法被编程绕过；
- provider、validation、tool、domain 失败可区分；
- 不启动网络也能证明 schema 和调用路径。

## Phase 2：按调用方切换

对照当前 [Chapter 7](../../07-specialists.md) 的完成态，逐条迁移：

```text
filing / extraction
  -> market research
  -> browser exploration
  -> supply chain
  -> global research
  -> API / CLI / persistence projections
```

每条路径的顺序是：

1. 先冻结业务输入、输出和失败合同；
2. 用 typed Agent 或 Pydantic Graph 实现新路径；
3. 在 application boundary 一次性切换调用方；
4. 比较领域结果和 trace，而不要求模型文本字节相同；
5. 删除该路径上已无调用方的旧实现和旧测试。

短期双路径只是迁移手段。如果 feature flag 没有删除日期、owner 和机械退出门，它就在变成
第二套永久 runtime。

### Gate B

- 所有生产调用方使用 typed Agent/Graph 路径；
- provider 故障不会切换回旧 LLM runtime；
- 旧 runtime 模块不再可 import；
- 持久化/API 中仍需要的字段由显式 projection 维持，不由隐式 wrapper 维持。

## Phase 3：删除旧 runtime

删除时不仅查文件名，还要查职责是否换了名字继续存在：

- 自定义 OpenAI tool-call while-loop；
- direct `chat.completions` 业务调用；
- generic `parse` / `complete` / JSON repair 兼容分支；
- provider 构造与密钥解析的重复实现；
- 只为旧 runtime 服务的 fixtures、flags 和 tests。

同时保留真正的领域资产：evidence/claim models、确定性评分、graph validation、安全、
人工审核、API/persistence 合同和 golden fixtures。

### Gate C：source/import gate

门禁应表达意图，而不仅匹配一个历史文件名：

```text
src/ 中不存在旧 runtime 实现；
业务模块不直接调用 provider SDK；
不存在 parse/complete 兼容分支或长期双 runtime flag；
Agent 声明 typed deps/output；
生产 toolset 经过 scope 与 execution-time permission check。
```

## Phase 4：用多层证据结束迁移

| 证据 | 要回答的问题 |
| --- | --- |
| schema/model tests | 类型、局部不变量和 retry 是否正确？ |
| tool/agent tests | schema exposure、权限、调用和失败语义是否正确？ |
| workflow tests | 状态转换、停止条件、预算和降级是否正确？ |
| fixed eval | grounding、工具选择、成本和 trace 是否恶化？ |
| live acceptance | 真实 provider 是否支持所需协议能力？ |
| source gate | 旧 runtime 是否真正不可达？ |

只有这些证据一起通过，cutover 才完成。回滚对象应是上一个可用部署 revision，
不是将已删除的旧 runtime 永久留在主干。
