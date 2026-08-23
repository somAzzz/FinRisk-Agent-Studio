# Docker Image Pinning

本仓库的 Compose 只管理 Neo4j，并固定为 `neo4j:5.26.0`。LLM 推理服务由外部
系统管理，其镜像、GPU 和模型版本不在本项目的 Docker 清单中。

## 固定策略

- 使用明确的小版本，不使用浮动 `latest`；
- 每季度检查 Neo4j release notes 与安全公告；
- 版本更新 PR 必须通过 CI，并执行 `docker compose up -d neo4j` smoke test；
- `docker compose config --services` 必须只输出 `neo4j`。

## 当前镜像

| Service | Image | Pinned version | Upstream |
| --- | --- | --- | --- |
| `neo4j` | `neo4j` | `5.26.0` | <https://neo4j.com/release-notes/> |

外部 SGLang/vLLM 版本应由其所属部署仓库记录，避免应用仓库与推理基础设施产生
重复且冲突的生命周期管理。
