#!/usr/bin/env bash
# Build and deploy ClinIQ Nexus to a Databricks App. The target app and workspace source folder are always explicit.
#
# Usage: tools/deploy.sh --profile <cli-profile> --warehouse <warehouse-id> --app <app-name> --path <workspace-folder>
#                        [--create] [--skip-build]
#   --create      create the app (from tools/app_spec.template.json) if it does not exist; without it, a missing app is an error
#   --skip-build  reuse the existing bundle in build/app-bundle
# Example (primary app): tools/deploy.sh --profile <p> --warehouse <id> --app cliniq-nexus \
#                          --path "/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-v5"
# The script refuses to write to the v4 rollback source folder (…/ClinIQ Nexus/app).
# See docs/03-deployment-and-rollback.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="$ROOT/build/app-bundle"
APP_NAME=""; SRC_PATH=""; PROFILE=""; WAREHOUSE_ID=""; BUILD=1; CREATE=0
while [ $# -gt 0 ]; do case "$1" in
  --profile) PROFILE="$2"; shift 2;; --warehouse) WAREHOUSE_ID="$2"; shift 2;; --app) APP_NAME="$2"; shift 2;;
  --path) SRC_PATH="$2"; shift 2;; --create) CREATE=1; shift;; --skip-build) BUILD=0; shift;;
  *) echo "unknown arg $1"; exit 2;; esac; done
[ -n "$PROFILE" ] && [ -n "$WAREHOUSE_ID" ] && [ -n "$APP_NAME" ] && [ -n "$SRC_PATH" ] || {
  echo "--profile, --warehouse, --app and --path are required (no default target)"; exit 2; }
case "${SRC_PATH%/}" in */ClinIQ\ Nexus/app) echo "Refusing to overwrite the v4 rollback source folder: $SRC_PATH"; exit 3;; esac
DB="databricks -p $PROFILE"

if ! $DB apps get "$APP_NAME" >/dev/null 2>&1; then
  [ "$CREATE" = 1 ] || { echo "app $APP_NAME not found; pass --create to create it"; exit 4; }
  NEW_APP=1
else
  NEW_APP=0
fi

[ "$BUILD" = 1 ] && "$ROOT/tools/build_bundle.sh"
[ -d "$BUNDLE" ] || { echo "bundle missing: $BUNDLE (run without --skip-build)"; exit 2; }
$DB workspace mkdirs "$SRC_PATH"
$DB workspace import-dir "$BUNDLE" "$SRC_PATH" --overwrite >/dev/null
echo "source uploaded to $SRC_PATH"

if [ "$NEW_APP" = 1 ]; then
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
