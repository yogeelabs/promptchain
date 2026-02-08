#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/disabled_dependency_example.yaml"
EXPECTED_ERROR="Cannot run stage 'use_items': dependency 'list_items' is disabled in pipeline yaml (enabled=false)."

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

OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" --topic chess 2>&1) && {
  echo "Example run failed: expected run to fail due to disabled dependency" >&2
  echo "$OUTPUT" >&2
  exit 1
}

if ! echo "$OUTPUT" | rg -q "$EXPECTED_ERROR"; then
  echo "Example run failed: missing expected dependency-disabled error" >&2
  echo "$OUTPUT" >&2
  exit 1
fi

RUN_DIR=$(ls -td runs/* 2>/dev/null | head -n1 || true)
if [[ -z "$RUN_DIR" ]]; then
  echo "Example run failed: run directory not found" >&2
  exit 1
fi

if ! rg -q "error=disabled_dependency" "$RUN_DIR/run.log"; then
  echo "Example run failed: disabled dependency log line missing" >&2
  exit 1
fi

echo "Example run passed: $RUN_DIR"
