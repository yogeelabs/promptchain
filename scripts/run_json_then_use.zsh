#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/json_then_use.yaml"
STAGE_JSON="list_items"
STAGE_MD="use_items"

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

OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" 2>&1) || {
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

if [[ ! -d "$RUN_DIR" ]]; then
  echo "Example run failed: run directory not created at $RUN_DIR" >&2
  exit 1
fi

OUTPUT_JSON="$RUN_DIR/stages/$STAGE_JSON/output.json"
if [[ ! -f "$OUTPUT_JSON" ]]; then
  echo "Example run failed: output.json missing for stage $STAGE_JSON" >&2
  exit 1
fi

OUTPUT_MD="$RUN_DIR/stages/$STAGE_MD/output.md"
if [[ ! -f "$OUTPUT_MD" ]]; then
  echo "Example run failed: output.md missing for stage $STAGE_MD" >&2
  exit 1
fi

echo "Example run passed: $RUN_DIR"
