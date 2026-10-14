#!/usr/bin/env bash
# Run the API + built frontend locally against the live Databricks workspace (read-only).
# Usage: tools/dev_server.sh [profile] [warehouse_id]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
PID=$(lsof -ti tcp:"$PORT" || true)
[ -n "$PID" ] && kill $PID && sleep 1
cd "$ROOT/app"
export DATABRICKS_CONFIG_PROFILE="${1:-${DATABRICKS_CONFIG_PROFILE:-cliniq}}"
export DATABRICKS_WAREHOUSE_ID="${2:-${DATABRICKS_WAREHOUSE_ID:?set DATABRICKS_WAREHOUSE_ID}}"
nohup "$ROOT/.venv/bin/uvicorn" backend.main:app --host 127.0.0.1 --port "$PORT" > "${LOG:-/tmp/cliniq-dev.log}" 2>&1 &
echo "started on :$PORT (log ${LOG:-/tmp/cliniq-dev.log})"
