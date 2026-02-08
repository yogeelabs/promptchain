#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi


PIPELINE="pipelines/mixed_models.yaml"
STAGE_ONE="draft"
STAGE_TWO="refine"

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

OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" --topic robotics 2>&1) || {
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

if [[ ! -f "$RUN_DIR/run.json" ]]; then
  echo "Example run failed: run.json missing" >&2
  exit 1
fi

if [[ ! -f "$RUN_DIR/logs/stages/$STAGE_ONE/raw.txt" ]]; then
  echo "Example run failed: $STAGE_ONE raw.txt missing" >&2
  exit 1
fi

if [[ ! -f "$RUN_DIR/stages/$STAGE_ONE/output.md" ]]; then
  echo "Example run failed: $STAGE_ONE output.md missing" >&2
  exit 1
fi

if [[ ! -f "$RUN_DIR/logs/stages/$STAGE_TWO/raw.txt" ]]; then
  echo "Example run failed: $STAGE_TWO raw.txt missing" >&2
  exit 1
fi

if [[ ! -f "$RUN_DIR/stages/$STAGE_TWO/output.md" ]]; then
  echo "Example run failed: $STAGE_TWO output.md missing" >&2
  exit 1
fi

echo "Example run passed: $RUN_DIR"
