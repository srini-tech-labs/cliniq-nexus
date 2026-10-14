#!/usr/bin/env bash
# Build the frontend and assemble the Databricks App source bundle in build/app-next.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/app-next"
(cd "$ROOT/app/frontend" && npm ci --no-audit --no-fund >/dev/null && npx tsc --noEmit -p . && npx vite build >/dev/null)
rm -rf "$OUT" && mkdir -p "$OUT/frontend"
cp "$ROOT/app/app.yaml" "$ROOT/app/requirements.txt" "$OUT/"
rsync -a --exclude "__pycache__" "$ROOT/app/backend" "$OUT/"
cp -r "$ROOT/app/frontend/dist" "$OUT/frontend/dist"
echo "bundle ready: $OUT ($(du -sh "$OUT" | cut -f1))"
