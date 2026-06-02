#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${OPENVIKING_AGENT_CONFIG:-config/config.yaml}"

openviking-agent --config "$CONFIG_PATH" validate-config
exec uvicorn backend.app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
