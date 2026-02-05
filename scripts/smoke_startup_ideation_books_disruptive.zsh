#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/startup_ideation_books_disruptive.yaml"
STAGE_IDS=("book_list" "book_lines")

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

if [[ ! -f "$RUN_DIR/run.json" ]]; then
  echo "Smoke check failed: run.json missing" >&2
  exit 1
fi

for STAGE_ID in "${STAGE_IDS[@]}"; do
  if [[ ! -f "$RUN_DIR/stages/$STAGE_ID/raw.txt" ]]; then
    echo "Smoke check failed: raw.txt missing for stage $STAGE_ID" >&2
    exit 1
  fi
  if [[ "$STAGE_ID" == "book_list" ]]; then
    if [[ ! -f "$RUN_DIR/stages/$STAGE_ID/output.json" ]]; then
      echo "Smoke check failed: output.json missing for stage $STAGE_ID" >&2
      exit 1
    fi
  else
    if [[ ! -f "$RUN_DIR/stages/$STAGE_ID/output.md" ]]; then
      echo "Smoke check failed: output.md missing for stage $STAGE_ID" >&2
      exit 1
    fi
  fi
  if [[ ! -f "$RUN_DIR/stages/$STAGE_ID/context.json" ]]; then
    echo "Smoke check failed: context.json missing for stage $STAGE_ID" >&2
    exit 1
  fi
  if [[ ! -f "$RUN_DIR/stages/$STAGE_ID/stage.json" ]]; then
    echo "Smoke check failed: stage.json missing for stage $STAGE_ID" >&2
    exit 1
  fi
done

echo "Smoke check passed: $RUN_DIR"
