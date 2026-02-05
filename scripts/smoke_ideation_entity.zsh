#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/ideation_entity.yaml"
INPUT="User playing chess"
STAGES=(
  atomic_decomposition
  core_entity_extraction
  ontology_level_decomposition
  exhaustive_state_space_entity_enumerator
  representation_aware_decomposition
  system_blueprint_prompt
)

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

if [[ "${1:-}" != "" ]]; then
  STAGE_FILTER="$1"
elif [[ "${STAGE:-}" != "" ]]; then
  STAGE_FILTER="$STAGE"
else
  STAGE_FILTER=""
fi

if [[ -n "$STAGE_FILTER" ]]; then
  OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" --input "$INPUT" --stage "$STAGE_FILTER" 2>&1) || {
    echo "Smoke check failed: promptchain run failed" >&2
    echo "$OUTPUT" >&2
    exit 1
  }
else
  OUTPUT=$($PYTHON_BIN -m promptchain.cli run --pipeline "$PIPELINE" --input "$INPUT" 2>&1) || {
    echo "Smoke check failed: promptchain run failed" >&2
    echo "$OUTPUT" >&2
    exit 1
  }
fi
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

if [[ -n "$STAGE_FILTER" ]]; then
  STAGES=("$STAGE_FILTER")
fi

for stage in $STAGES; do
  STAGE_DIR="$RUN_DIR/stages/$stage"
  RAW_FILE="$RUN_DIR/logs/stages/$stage/raw.txt"
  OUT_FILE="$STAGE_DIR/output.md"

  if [[ ! -d "$STAGE_DIR" ]]; then
    echo "Smoke check failed: stage directory missing for $stage" >&2
    exit 1
  fi

  if [[ ! -f "$RAW_FILE" ]]; then
    echo "Smoke check failed: raw output missing for $stage" >&2
    exit 1
  fi

  if [[ ! -f "$OUT_FILE" ]]; then
    echo "Smoke check failed: output.md missing for $stage" >&2
    exit 1
  fi
done

echo "Smoke check passed: $PIPELINE"
