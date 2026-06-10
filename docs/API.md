# OpenSkald API Reference

[Docs](README.md) · English / [中文](API_CN.md)

This document describes the FastAPI routes exposed under `/api`. It is based on the
current implementation in `backend/app/api/routes.py`.

## Basics

Default local base URL:

```text
http://localhost:8000/api
```

All request and response bodies are JSON. The API currently has no authentication layer;
run it behind trusted network controls or a reverse proxy when deploying beyond local
development.

Common enums:

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

Common query parameters:

| Name | Used By | Notes |
| --- | --- | --- |
| `status` | review and skill proposal listing | One `ReviewStatus` value |
| `platform` | review, failures, timeline | Example: `blog`, `wechat`, `x`, `xiaohongshu` |
| `limit` | searches, timeline, records, runs | Integer from 1 to 100, default `20` |
| `q` | search endpoints | Plain substring search |

## End-to-end Workflow

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

If generation has no indexed articles and no readable knowledge files, `POST /generate`
returns `409` with `No OpenViking articles available for generation`.

## Service And Config

### `GET /health`

Returns a compact health payload.

Example:

```bash
curl http://localhost:8000/api/health
```

Response fields:

| Field | Description |
| --- | --- |
| `status` | `ok` when there are no config issues, otherwise `degraded` |
| `config_errors` | Error-level config issue messages |
| `reflector` | Reflection subsystem marker |
| `skills` | Loaded skill names |
| `publishers` | Loaded publisher names |
| `scheduler_jobs` | Active scheduler job IDs |

### `GET /config/summary`

Returns a redacted runtime config summary.

```bash
curl http://localhost:8000/api/config/summary
```

Secrets are not returned. The response shows env var names and boolean configured status.

### `GET /status`

Returns operational status across config, scheduler, knowledge, memory, skills, and
publishers.

```bash
curl http://localhost:8000/api/status
```

Important response areas:

| Field | Description |
| --- | --- |
| `ok` | False when config has error-level issues |
| `scheduler.jobs` | Job IDs and next run times |
| `knowledge` | Configured path, existence, and indexed article count |
| `memory` | Article, content, and skill proposal summaries |
| `skills.loaded` | Loaded skill names |
This document provides the complete API reference for OpenSkald.

## Knowledge

### `POST /knowledge/ingest`

Reads the configured local knowledge path and stores recent articles in the article index.

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest
```

Response example:

```json
{
  "ingested": 2
}
```

### `GET /knowledge/articles`

Lists indexed articles.

```bash
curl http://localhost:8000/api/knowledge/articles
```

Article shape:

```json
{
  "id": "3ef...",
  "title": "RAG Operations",
  "content": "Production retrieval needs...",
  "source_path": "examples/knowledge/rag-agent-memory.md",
  "url": null,
  "tags": ["rag"],
  "created_at": null
}
```

### `GET /knowledge/search`

Searches indexed articles by title, content, and tags.

```bash
curl "http://localhost:8000/api/knowledge/search?q=retrieval&limit=10"
```

An empty `q` returns an empty list.

## Generation

### `POST /generate`

Generates one or more reviewable drafts for requested platforms.

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"content_type":"daily_summary","platforms":["blog","wechat","x","xiaohongshu"]}'
```

Request body:

```json
{
  "content_type": "daily_summary",
  "platforms": ["blog", "x"]
}
```

Response shape is a list of `GeneratedContent` objects:

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

Errors:

| Status | When |
| --- | --- |
| `409` | No articles are available or another generation precondition fails |
| `502` | LLM provider request fails or returns an unexpected shape |

## Review And Content State

### `GET /review`

Lists generated content, optionally filtered by status and platform.

```bash
curl "http://localhost:8000/api/review?status=pending_review&platform=x"
```

### `POST /review/{content_id}/approve`

Marks a content item as `approved`.

```bash
curl -X POST http://localhost:8000/api/review/<content_id>/approve
```

Returns the updated content item. Also records an approval experience in memory.

Errors:

| Status | When |
| --- | --- |
| `404` | Content ID is not found |

### `POST /review/{content_id}/reject`

Marks a content item as `rejected` and stores a review note.

```bash
curl -X POST http://localhost:8000/api/review/<content_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"Needs more source detail before publishing."}'
```

Request body:

```json
{
  "reason": "Needs more source detail before publishing."
}
```

### `GET /content/summary`

Summarizes all generated content by status, platform, and failure state.

```bash
curl http://localhost:8000/api/content/summary
```

### `GET /content/failures`

Lists content items that have `last_publish_error` or `publish_validation_errors` in
metadata.

```bash
curl "http://localhost:8000/api/content/failures?platform=x"
```

## Memory

### `GET /memory/timeline`

Lists recent content events ordered by publish, review, or creation time.

```bash
curl "http://localhost:8000/api/memory/timeline?platform=x&limit=10"
```

Timeline event shape:

```json
{
  "id": "content-id",
  "content_type": "daily_summary",
  "platform": "x",
  "title": "Daily Summary for x",
  "status": "pending_review",
  "created_at": "2026-06-08T00:00:00+00:00",
  "reviewed_at": null,
  "published_at": null,
  "skill": "x_writer",
  "last_publish_error": null
}
```

### `GET /memory/search`

Searches generated content by title, body, platform, content type, and metadata.

```bash
curl "http://localhost:8000/api/memory/search?q=retrieval&limit=10"
```

### `GET /memory/records`

Searches namespaced memory records.

```bash
curl "http://localhost:8000/api/memory/records?namespace=viking://agent/experience&kind=experience&limit=10"
```

Default namespace is `viking://`.

### `GET /memory/reflections`

Lists reflection records.

```bash
curl "http://localhost:8000/api/memory/reflections?limit=10"
```

### `POST /memory/reflections/discover`

Runs reflection discovery over recent experiences and stores generated reflections.

```bash
curl -X POST http://localhost:8000/api/memory/reflections/discover
```

## Metrics

### `POST /metrics/import`

Imports external numeric metrics for growth analysis.

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

Request body:

```json
{
  "metrics": [
    {
      "metric_name": "views",
      "value": 1280,
      "dimensions": {"platform": "blog"},
      "observed_at": "2026-06-08T00:00:00Z"
    }
  ]
}
```

Response:

```json
{
  "ok": true,
  "imported": 1
}
```

## Agent Runs

### `POST /agent/runs`

Executes an OpenSkald agent run and records the run lifecycle.

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

Request body:

```json
{
  "objective": "Create a practical RAG operations thread",
  "content_type": "daily_summary",
  "platforms": ["x"],
  "mode": "single"
}
```

`mode` defaults to `single`. Any value other than `collaborative` is treated as `single`
by the current route implementation.

In `single` mode the runtime calls `ContentAgent.generate`. In `collaborative` mode it
uses `MultiAgentOrchestrator` to research, write, review, optionally revise, store
`pending_review` content, reflect, and run growth analysis. The current collaborative
workflow does not publish content automatically.

Response fields include:

| Field | Description |
| --- | --- |
| `id` | Agent run ID |
| `mode` | `single` or `collaborative` |
| `status` | `completed`, `partial`, or `failed` after execution |
| `input` | Objective |
| `output` | Summary string |
| `artifacts` | Generated content or orchestrator artifacts |
| `memory_writes` | Count of memory writes from the run |
| `latency_ms` | Runtime latency |
| `errors` | Runtime or agent errors |

### `GET /agent/runs`

Lists recent completed run states.

```bash
curl "http://localhost:8000/api/agent/runs?limit=10"
```

### `GET /agent/runs/{run_id}`

Fetches one stored run.

```bash
curl http://localhost:8000/api/agent/runs/<run_id>
```

Errors:

| Status | When |
| --- | --- |
| `404` | Agent run ID is not found |

## Publishing

### `GET /publishers/{platform}/check`

Checks one publisher.

```bash
curl http://localhost:8000/api/publishers/x/check
```

Dry-run publishers do not contact external APIs and return a message such as
`dry-run mode; X API was not contacted`.

Errors:

| Status | When |
| --- | --- |
| `404` | Publisher is not configured or loaded |

### `GET /publishers/checks`

Checks every loaded publisher.

```bash
curl http://localhost:8000/api/publishers/checks
```

### `GET /publish/{platform}/{content_id}/validate`

Runs platform validation without publishing.

```bash
curl http://localhost:8000/api/publish/x/<content_id>/validate
```

Response:

```json
{
  "ok": true,
  "errors": []
}
```

Validation examples:

| Platform | Validation |
| --- | --- |
| `blog` | Markdown heading required, body at least 200 characters |
| `wechat` | Markdown heading required, body at least 200 characters |
| `x` | Each non-empty line must be 280 characters or fewer |
| `xiaohongshu` | Body should include cover prompts; title should be 40 characters or fewer |

### `POST /publish/{platform}/{content_id}`

Publishes a single content item.

```bash
curl -X POST http://localhost:8000/api/publish/blog/<content_id>
```

Preconditions:

- Content ID exists.
- Request platform matches `content.platform`.
- If `review.require_human_approval` is true, content status must be `approved`.
- Publisher must be enabled.
- Publisher validation must pass.

Success response is a `PublishResult`:

```json
{
  "platform": "blog",
  "content_id": "content-id",
  "dry_run": false,
  "external_id": "daily-summary-for-blog",
  "url": "data/blog/daily-summary-for-blog.md",
  "title": "Daily Summary for blog",
  "metadata": {"output_path": "data/blog/daily-summary-for-blog.md"}
}
```

Errors:

| Status | When |
| --- | --- |
| `404` | Content ID is not found |
| `409` | Approval is required, platform mismatch, publisher disabled, validation failed, or publish failed |

When publishing fails, the content remains approved. Inspect:

```bash
curl "http://localhost:8000/api/content/failures?platform=x"
curl http://localhost:8000/api/content/summary
```

## Skill Proposals

### `GET /skills/proposals`

Lists skill proposals.

```bash
curl "http://localhost:8000/api/skills/proposals?status=pending_review"
```

### `POST /skills/proposals`

Creates a human-gated skill proposal.

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

Request body:

```json
{
  "title": "Architecture comparison writer",
  "reason": "Repeated posts need a reusable prompt.",
  "proposed_skill_name": "architecture_comparison_writer",
  "draft_prompt": "Compare these articles.\n\n{articles}",
  "content_types": ["deep_technical_analysis"],
  "platforms": ["wechat"]
}
```

### `POST /skills/proposals/discover`

Discovers proposals from stored memory patterns.

```bash
curl -X POST http://localhost:8000/api/skills/proposals/discover
```

Discovery only creates pending proposals.

### `POST /skills/proposals/{proposal_id}/approve`

Approves a proposal and materializes a disabled draft skill.

```bash
curl -X POST http://localhost:8000/api/skills/proposals/<proposal_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"note":"Create disabled draft for review."}'
```

Request body:

```json
{
  "note": "Create disabled draft for review."
}
```

Errors:

| Status | When |
| --- | --- |
| `404` | Proposal ID is not found |

### `POST /skills/proposals/{proposal_id}/reject`

Rejects a proposal with a reason.

```bash
curl -X POST http://localhost:8000/api/skills/proposals/<proposal_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"Too broad for one reusable skill."}'
```

Request body:

```json
{
  "reason": "Too broad for one reusable skill."
}
```

## CLI Equivalents

Most API workflows have matching CLI commands:

| API Workflow | CLI |
| --- | --- |
| `GET /config/summary` | `OpenSkald config-summary` |
| `GET /status` | `OpenSkald status` |
| `POST /knowledge/ingest` | `OpenSkald knowledge-ingest` |
| `GET /knowledge/search` | `OpenSkald knowledge-list --query ...` |
| `POST /generate` | `OpenSkald generate-once --content-type ... --platform ...` |
| `GET /review` | `OpenSkald review-list` |
| approve/reject | `OpenSkald review-approve` / `review-reject` |
| publish one item | `OpenSkald publish-content --content-id ...` |
| check publishers | `OpenSkald publisher-check` / `publisher-check-all` |
| list failures | `OpenSkald content-failures` |
| memory search | `OpenSkald memory-search --query ...` |
| agent run | `OpenSkald agent-run --objective ...` |

## Error Handling Notes

- Config errors make `/api/status` return `"ok": false`; `/api/health` can report
  `degraded` when config issues exist.
- LLM errors from generation are surfaced as `502`.
- Publishing validation and runtime failures are surfaced as `409`.
- Publishing failures are persisted in content metadata under `last_publish_error`,
  `publish_errors`, or `publish_validation_errors`.
- Secret values are not exposed by config endpoints.
