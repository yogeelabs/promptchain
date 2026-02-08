#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/disabled_stage_example.yaml"
DISABLED_STAGE="intro"
ENABLED_STAGE="summary"

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

META_FILE="$RUN_DIR/${DISABLED_STAGE}.meta.json"
if [[ ! -f "$META_FILE" ]]; then
  echo "Example run failed: meta file missing for disabled stage" >&2
  exit 1
fi

$PYTHON_BIN - <<PY
import json
from pathlib import Path

meta = json.loads(Path("$META_FILE").read_text())
if meta.get("status") != "skipped":
    raise SystemExit("Example run failed: disabled stage not marked skipped")
if meta.get("skip_reason") != "disabled_in_yaml":
    raise SystemExit("Example run failed: skip_reason not set to disabled_in_yaml")
PY

if ! rg -q "Stage ${DISABLED_STAGE} SKIPPED \\(disabled in pipeline yaml\\)" "$RUN_DIR/run.log"; then
  echo "Example run failed: skip log line missing" >&2
  exit 1
fi

if [[ ! -f "$RUN_DIR/stages/$ENABLED_STAGE/output.md" ]]; then
  echo "Example run failed: enabled stage output missing" >&2
  exit 1
fi

echo "Example run passed: $RUN_DIR"
