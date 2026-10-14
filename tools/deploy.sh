#!/usr/bin/env bash
# Build and deploy ClinIQ Nexus to a Databricks App (default: the candidate app cliniq-nexus-next).
#
# Usage: tools/deploy.sh --profile <cli-profile> --warehouse <warehouse-id> [--app cliniq-nexus-next]
#                        [--path "/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-next"] [--skip-build]
# The script never modifies the legacy app source folder. Switching the production app is a separate,
# explicit step documented in docs/03-deployment-and-rollback.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="cliniq-nexus-next"; SRC_PATH="/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-next"; PROFILE=""; WAREHOUSE_ID=""; BUILD=1
while [ $# -gt 0 ]; do case "$1" in
  --profile) PROFILE="$2"; shift 2;; --warehouse) WAREHOUSE_ID="$2"; shift 2;; --app) APP_NAME="$2"; shift 2;;
  --path) SRC_PATH="$2"; shift 2;; --skip-build) BUILD=0; shift;; *) echo "unknown arg $1"; exit 2;; esac; done
[ -n "$PROFILE" ] && [ -n "$WAREHOUSE_ID" ] || { echo "--profile and --warehouse are required"; exit 2; }
case "$SRC_PATH" in */ClinIQ\ Nexus/app) echo "Refusing to overwrite the legacy app folder"; exit 3;; esac
DB="databricks -p $PROFILE"

[ "$BUILD" = 1 ] && "$ROOT/tools/build_bundle.sh"
$DB workspace mkdirs "$SRC_PATH"
$DB workspace import-dir "$ROOT/build/app-next" "$SRC_PATH" --overwrite >/dev/null
echo "source uploaded to $SRC_PATH"

if ! $DB apps get "$APP_NAME" >/dev/null 2>&1; then
  export APP_NAME WAREHOUSE_ID
  envsubst < "$ROOT/tools/app_spec.template.json" > "$ROOT/build/app_spec.json"
  $DB apps create --json @"$ROOT/build/app_spec.json" >/dev/null
  echo "created app $APP_NAME"
fi
SP=$($DB apps get "$APP_NAME" -o json | python3 -c "import json,sys;print(json.load(sys.stdin)['service_principal_client_id'])")
for stmt in "GRANT USE CATALOG ON CATALOG healthcare TO \`$SP\`" "GRANT USE SCHEMA, SELECT ON SCHEMA healthcare.cliniq_v5_stage TO \`$SP\`"; do
  $DB api post /api/2.0/sql/statements --json "{\"warehouse_id\":\"$WAREHOUSE_ID\",\"statement\":\"$stmt\",\"wait_timeout\":\"50s\"}" >/dev/null
done
echo "read-only grants ensured for service principal $SP"
$DB apps deploy "$APP_NAME" --source-code-path "$SRC_PATH" -o json | python3 -c "import json,sys;d=json.load(sys.stdin);print('deployment',d['deployment_id'],d['status']['state'])"
URL=$($DB apps get "$APP_NAME" -o json | python3 -c "import json,sys;print(json.load(sys.stdin)['url'])")
"$ROOT/.venv/bin/python" "$ROOT/tools/smoke_test.py" "$URL" "$PROFILE"
