# OpenSkald API 参考

[文档](README_CN.md) · [English](API.md) / 中文

本文档说明 `/api` 下暴露的 FastAPI 路由，依据当前
`backend/app/api/routes.py` 实现整理。

## 基础信息

默认本地地址：

```text
http://localhost:8000/api
```

所有请求和响应都是 JSON。当前 API 没有内置鉴权层；如果不只是本地开发，请放在
可信网络、网关或反向代理后使用。

常用枚举：

```text
ContentType:
  daily_summary
  weekly_summary
  hot_topic_analysis
  deep_technical_analysis

ReviewStatus:
  draft
  pending_review
  approved
  rejected
  published

Agent mode:
  single
  collaborative
```

常用查询参数：

| 参数 | 使用场景 | 说明 |
| --- | --- | --- |
| `status` | 审核队列、Skill 提案列表 | 一个 `ReviewStatus` 值 |
| `platform` | 审核、失败列表、时间线 | 例如 `blog`、`wechat`、`x`、`xiaohongshu` |
| `limit` | 搜索、时间线、记录、运行列表 | 1 到 100 的整数，默认 `20` |
| `q` | 搜索接口 | 普通子字符串搜索 |

## 端到端流程

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest

curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"content_type":"daily_summary","platforms":["blog","x"]}'

curl "http://localhost:8000/api/review?status=pending_review"

curl -X POST http://localhost:8000/api/review/<content_id>/approve

curl http://localhost:8000/api/publish/blog/<content_id>/validate

curl -X POST http://localhost:8000/api/publish/blog/<content_id>
```

如果没有已索引文章，也没有可读取的知识文件，`POST /generate` 会返回 `409`，
错误信息为 `No OpenViking articles available for generation`。

## 服务与配置

### `GET /health`

返回简短健康状态。

```bash
curl http://localhost:8000/api/health
```

关键字段：

| 字段 | 说明 |
| --- | --- |
| `status` | 无配置问题时为 `ok`，否则为 `degraded` |
| `config_errors` | error 级别配置问题 |
| `skills` | 已加载 Skill 名称 |
| `publishers` | 已加载 Publisher 名称 |
| `scheduler_jobs` | 当前启用的定时任务 ID |

### `GET /config/summary`

返回脱敏后的运行时配置摘要。

```bash
curl http://localhost:8000/api/config/summary
```

不会返回密钥值，只显示环境变量名以及是否已配置。

### `GET /status`

返回配置、定时任务、知识库、Memory、Skill 和 Publisher 的运行状态。

```bash
curl http://localhost:8000/api/status
```

## 知识库

### `POST /knowledge/ingest`

读取配置的本地知识路径，将最近文章写入文章索引。

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest
```

响应示例：

```json
{
  "ingested": 2
}
```

### `GET /knowledge/articles`

列出已索引文章。

```bash
curl http://localhost:8000/api/knowledge/articles
```

### `GET /knowledge/search`

按标题、正文和标签搜索已索引文章。

```bash
curl "http://localhost:8000/api/knowledge/search?q=retrieval&limit=10"
```

空 `q` 会返回空列表。

## 内容生成

### `POST /generate`

为指定平台生成一条或多条待审核内容。

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"content_type":"daily_summary","platforms":["blog","wechat","x","xiaohongshu"]}'
```

请求体：

```json
{
  "content_type": "daily_summary",
  "platforms": ["blog", "x"]
}
```

响应是 `GeneratedContent` 列表：

```json
[
  {
    "id": "content-id",
    "content_type": "daily_summary",
    "platform": "x",
    "title": "Daily Summary for x",
    "body": "1/ ...",
    "metadata": {
      "skill": "x_writer",
      "article_count": 2,
      "article_source": "index"
    },
    "status": "pending_review",
    "created_at": "2026-06-08T00:00:00Z",
    "reviewed_at": null,
    "review_note": null,
    "published_at": null
  }
]
```

错误：

| 状态码 | 场景 |
| --- | --- |
| `409` | 没有可用文章，或生成前置条件不满足 |
| `502` | LLM Provider 请求失败或响应结构异常 |

## 审核与内容状态

### `GET /review`

列出生成内容，可按状态和平台过滤。

```bash
curl "http://localhost:8000/api/review?status=pending_review&platform=x"
```

### `POST /review/{content_id}/approve`

将内容标记为 `approved`。

```bash
curl -X POST http://localhost:8000/api/review/<content_id>/approve
```

### `POST /review/{content_id}/reject`

将内容标记为 `rejected`，并保存审核原因。

```bash
curl -X POST http://localhost:8000/api/review/<content_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"Needs more source detail before publishing."}'
```

### `GET /content/summary`

按状态、平台和失败情况汇总内容。

```bash
curl http://localhost:8000/api/content/summary
```

### `GET /content/failures`

列出 metadata 中存在 `last_publish_error` 或 `publish_validation_errors` 的内容。

```bash
curl "http://localhost:8000/api/content/failures?platform=x"
```

## Memory

### `GET /memory/timeline`

按发布时间、审核时间或创建时间倒序列出内容事件。

```bash
curl "http://localhost:8000/api/memory/timeline?platform=x&limit=10"
```

### `GET /memory/search`

按标题、正文、平台、内容类型和 metadata 搜索生成内容。

```bash
curl "http://localhost:8000/api/memory/search?q=retrieval&limit=10"
```

### `GET /memory/records`

按 namespace 查询 MemoryRecord。

```bash
curl "http://localhost:8000/api/memory/records?namespace=viking://agent/experience&kind=experience&limit=10"
```

### `GET /memory/reflections`

列出反思记录。

```bash
curl "http://localhost:8000/api/memory/reflections?limit=10"
```

### `POST /memory/reflections/discover`

基于近期经验触发反思发现。

```bash
curl -X POST http://localhost:8000/api/memory/reflections/discover
```

## 指标

### `POST /metrics/import`

导入外部数值指标，供增长分析使用。

```bash
curl -X POST http://localhost:8000/api/metrics/import \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {
        "metric_name": "views",
        "value": 1280,
        "dimensions": {"platform": "blog", "content_id": "content-id"}
      }
    ]
  }'
```

响应：

```json
{
  "ok": true,
  "imported": 1
}
```

## Agent Runs

### `POST /agent/runs`

执行一次 OpenSkald Agent Run，并记录运行生命周期。

```bash
curl -X POST http://localhost:8000/api/agent/runs \
  -H "Content-Type: application/json" \
  -d '{
    "objective":"Create a practical RAG operations thread",
    "content_type":"daily_summary",
    "platforms":["x"],
    "mode":"single"
  }'
```

`mode` 默认为 `single`。当前路由中，除 `collaborative` 外的值都会按 `single` 处理。

`single` 模式会调用 `ContentAgent.generate`。`collaborative` 模式会使用
`MultiAgentOrchestrator` 执行 research、write、review、可选 revise、存储
`pending_review` 内容、reflection 和 growth analysis。当前 collaborative
流程不会自动发布内容。

### `GET /agent/runs`

列出最近 Agent Run。

```bash
curl "http://localhost:8000/api/agent/runs?limit=10"
```

### `GET /agent/runs/{run_id}`

查询单个 Agent Run。

```bash
curl http://localhost:8000/api/agent/runs/<run_id>
```

## 发布

### `GET /publishers/{platform}/check`

检查单个平台发布器。

```bash
curl http://localhost:8000/api/publishers/x/check
```

dry-run 发布器不会访问外部 API。

### `GET /publishers/checks`

检查所有已加载发布器。

```bash
curl http://localhost:8000/api/publishers/checks
```

### `GET /publish/{platform}/{content_id}/validate`

只执行发布前校验，不发布。

```bash
curl http://localhost:8000/api/publish/x/<content_id>/validate
```

响应：

```json
{
  "ok": true,
  "errors": []
}
```

平台校验：

| 平台 | 校验规则 |
| --- | --- |
| `blog` | 需要 Markdown 标题，正文至少 200 字符 |
| `wechat` | 需要 Markdown 标题，正文至少 200 字符 |
| `x` | 每个非空行不超过 280 字符 |
| `xiaohongshu` | 正文应包含封面提示词，标题不超过 40 字符 |

### `POST /publish/{platform}/{content_id}`

发布单条内容。

```bash
curl -X POST http://localhost:8000/api/publish/blog/<content_id>
```

前置条件：

- 内容 ID 存在。
- URL 中的平台与 `content.platform` 一致。
- 如果 `review.require_human_approval` 为 true，内容必须是 `approved`。
- Publisher 必须启用。
- Publisher 校验必须通过。

发布失败时内容会保持 `approved`，错误会写入 metadata，可修复后重试。

## Skill 提案

### `GET /skills/proposals`

列出 Skill 提案。

```bash
curl "http://localhost:8000/api/skills/proposals?status=pending_review"
```

### `POST /skills/proposals`

创建人工把关的 Skill 提案。

```bash
curl -X POST http://localhost:8000/api/skills/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Architecture comparison writer",
    "reason":"Repeated architecture comparison posts need a reusable prompt.",
    "proposed_skill_name":"architecture_comparison_writer",
    "draft_prompt":"Compare these articles and produce a practical architecture note.\n\n{articles}",
    "content_types":["deep_technical_analysis"],
    "platforms":["wechat"]
  }'
```

### `POST /skills/proposals/discover`

从已存储 Memory 模式中发现提案。

```bash
curl -X POST http://localhost:8000/api/skills/proposals/discover
```

### `POST /skills/proposals/{proposal_id}/approve`

批准提案，并生成 disabled 的草稿 Skill。

```bash
curl -X POST http://localhost:8000/api/skills/proposals/<proposal_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"note":"Create disabled draft for review."}'
```

### `POST /skills/proposals/{proposal_id}/reject`

拒绝提案。

```bash
curl -X POST http://localhost:8000/api/skills/proposals/<proposal_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"Too broad for one reusable skill."}'
```

## CLI 对照

| API 流程 | CLI |
| --- | --- |
| `GET /config/summary` | `OpenSkald config-summary` |
| `GET /status` | `OpenSkald status` |
| `POST /knowledge/ingest` | `OpenSkald knowledge-ingest` |
| `GET /knowledge/search` | `OpenSkald knowledge-list --query ...` |
| `POST /generate` | `OpenSkald generate-once --content-type ... --platform ...` |
| `GET /review` | `OpenSkald review-list` |
| 审核 approve/reject | `OpenSkald review-approve` / `review-reject` |
| 发布单条内容 | `OpenSkald publish-content --content-id ...` |
| 检查发布器 | `OpenSkald publisher-check` / `publisher-check-all` |
| 失败列表 | `OpenSkald content-failures` |
| Memory 搜索 | `OpenSkald memory-search --query ...` |
| Agent Run | `OpenSkald agent-run --objective ...` |

## 错误处理

- 配置错误会让 `/api/status` 返回 `"ok": false`。
- LLM 生成错误会以 `502` 返回。
- 发布校验和发布运行错误会以 `409` 返回。
- 发布失败会持久化到内容 metadata，例如 `last_publish_error`、
  `publish_errors` 或 `publish_validation_errors`。
- 配置接口不会暴露密钥值。
