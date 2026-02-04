#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/json_file_fanout.yaml"
MAP_STAGE="describe_item"

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Smoke check failed: python not found" >&2
  exit 1
fi

if [[ ! -f "$PIPELINE" ]]; then
  echo "Smoke check failed: pipeline not found at $PIPELINE" >&2
  exit 1
fi

OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" 2>&1) || {
  echo "Smoke check failed: promptchain run failed" >&2
  echo "$OUTPUT" >&2
  exit 1
}

RUN_DIR=$(echo "$OUTPUT" | rg -m1 '^run_dir:' | awk '{print $2}')
if [[ -z "$RUN_DIR" ]]; then
  echo "Smoke check failed: run_dir not reported" >&2
  echo "$OUTPUT" >&2
  exit 1
fi

if [[ ! -d "$RUN_DIR" ]]; then
  echo "Smoke check failed: run directory not created at $RUN_DIR" >&2
  exit 1
fi

MAP_MANIFEST="$RUN_DIR/stages/$MAP_STAGE/output.json"
if [[ ! -f "$MAP_MANIFEST" ]]; then
  echo "Smoke check failed: output.json missing for map stage $MAP_STAGE" >&2
  exit 1
fi

$PYTHON_BIN - <<PY
import json
from pathlib import Path

run_dir = Path("$RUN_DIR")
map_manifest = run_dir / "stages" / "$MAP_STAGE" / "output.json"
manifest = json.loads(map_manifest.read_text())
items = manifest.get("items")
if not isinstance(items, list) or not items:
    raise SystemExit("Smoke check failed: map manifest items missing")

any_completed = False
for entry in items:
    if entry.get("status") == "completed":
        any_completed = True
        output_path = entry.get("output_path")
        if not output_path:
            raise SystemExit("Smoke check failed: completed item missing output_path")
        if not (run_dir / output_path).exists():
            raise SystemExit("Smoke check failed: item output file missing")
        raw_path = entry.get("raw_path")
        if raw_path and not (run_dir / raw_path).exists():
            raise SystemExit("Smoke check failed: item raw file missing")

if not any_completed:
    raise SystemExit("Smoke check failed: no completed map items")

print("Smoke check passed:", map_manifest)
PY
