#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi


PIPELINE="pipelines/json_list.yaml"
STAGE_ID="list_items"

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

OUTPUT_JSON="$RUN_DIR/stages/$STAGE_ID/output.json"
if [[ ! -f "$OUTPUT_JSON" ]]; then
  echo "Smoke check failed: output.json missing for stage $STAGE_ID" >&2
  exit 1
fi

$PYTHON_BIN - <<PY
import json
from pathlib import Path

path = Path("$OUTPUT_JSON")
data = json.loads(path.read_text())
if not isinstance(data, dict) or "items" not in data or not isinstance(data["items"], list):
    raise SystemExit("Smoke check failed: output.json missing items list")
if not data["items"]:
    raise SystemExit("Smoke check failed: items list is empty")
for idx, item in enumerate(data["items"], start=1):
    if not isinstance(item, dict):
        raise SystemExit(f"Smoke check failed: item {idx} is not an object")
    if "id" not in item:
        raise SystemExit(f"Smoke check failed: item {idx} missing id")
    if "_selected" not in item:
        raise SystemExit(f"Smoke check failed: item {idx} missing _selected")
print("Smoke check passed:", path)
PY
