#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/openai_batch_map.yaml"
MAP_STAGE="expand_items"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Example run skipped: OPENAI_API_KEY is not set" >&2
  exit 0
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Example run failed: python not found" >&2
  exit 1
fi

if [[ ! -f "$PIPELINE" ]]; then
  echo "Example run failed: pipeline not found at $PIPELINE" >&2
  exit 1
fi

OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" --topic chess 2>&1) || {
  echo "Example run failed: promptchain run failed" >&2
  echo "$OUTPUT" >&2
  exit 1
}

RUN_DIR=$(echo "$OUTPUT" | rg -m1 '^run_dir:' | awk '{print $2}')
if [[ -z "$RUN_DIR" ]]; then
  echo "Example run failed: run_dir not reported" >&2
  echo "$OUTPUT" >&2
  exit 1
fi

STAGE_META="$RUN_DIR/${MAP_STAGE}.meta.json"
if [[ ! -f "$STAGE_META" ]]; then
  echo "Example run failed: stage meta missing for $MAP_STAGE" >&2
  exit 1
fi

BATCH_STATE="$RUN_DIR/support/stages/$MAP_STAGE/batch.json"
if [[ ! -f "$BATCH_STATE" ]]; then
  echo "Example run failed: batch state missing for $MAP_STAGE" >&2
  exit 1
fi

$PYTHON_BIN - <<PY
import json
from pathlib import Path

meta = json.loads(Path("$STAGE_META").read_text())
if meta.get("execution_mode") != "batch":
    raise SystemExit("Example run failed: execution_mode is not batch")

state = json.loads(Path("$BATCH_STATE").read_text())
if not state.get("batch_id"):
    raise SystemExit("Example run failed: batch_id missing")

print("Example run passed:", "$RUN_DIR")
PY
