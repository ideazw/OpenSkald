#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 0 ]]; then
  CONFIG_PATH="$1"
  WORK_DIR=""
else
  WORK_DIR="$(mktemp -d)"
  CONFIG_PATH="$WORK_DIR/demo-check.yaml"
  cat > "$CONFIG_PATH" <<EOF
environment: test
log_level: INFO

llm:
  provider: demo
  model: demo-local-deterministic

openviking:
  knowledge_base_path: examples/knowledge
  include_globs:
    - "**/*.md"
  max_articles_per_run: 5

scheduler: {}

publishers:
  blog:
    enabled: true
    account_id: $WORK_DIR/blog
    dry_run: false
    credentials_env: null
  wechat:
    enabled: false
    account_id: demo-wechat
    dry_run: true
    credentials_env: WECHAT_PUBLISHER_CREDENTIALS
  x:
    enabled: false
    account_id: demo-x
    dry_run: true
    credentials_env: X_PUBLISHER_CREDENTIALS
  xiaohongshu:
    enabled: false
    account_id: demo-xhs
    dry_run: true
    credentials_env: XIAOHONGSHU_PUBLISHER_CREDENTIALS

review:
  require_human_approval: true
  storage_path: $WORK_DIR/review.jsonl

memory:
  storage_path: $WORK_DIR/memory.jsonl
  skill_proposals_path: $WORK_DIR/skill_proposals.jsonl
  article_index_path: $WORK_DIR/articles.jsonl
EOF
  trap 'rm -rf "$WORK_DIR"' EXIT
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=(".venv/bin/python")
  RUFF=(".venv/bin/ruff")
  CLI=("${PYTHON[@]}" -m backend.app.cli)
else
  uv sync --extra dev
  PYTHON=(uv run python)
  RUFF=(uv run ruff)
  CLI=(uv run openviking-agent)
fi

"${PYTHON[@]}" -m pytest
"${RUFF[@]}" check .

"${CLI[@]}" --config "$CONFIG_PATH" validate-config
"${CLI[@]}" --config "$CONFIG_PATH" knowledge-ingest
"${CLI[@]}" --config "$CONFIG_PATH" status
"${CLI[@]}" --config "$CONFIG_PATH" publisher-check-all
"${CLI[@]}" --config "$CONFIG_PATH" generate-once \
  --content-type daily_summary \
  --platform blog \
  --platform x
"${CLI[@]}" --config "$CONFIG_PATH" review-list --status pending_review
