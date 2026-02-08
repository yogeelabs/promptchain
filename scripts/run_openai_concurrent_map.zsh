#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PIPELINE="pipelines/openai_concurrent_map.yaml"
LIST_STAGE="list_items"
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

LIST_JSON="$RUN_DIR/stages/$LIST_STAGE/output.json"
if [[ ! -f "$LIST_JSON" ]]; then
  echo "Example run failed: output.json missing for stage $LIST_STAGE" >&2
  exit 1
fi

MAP_MANIFEST="$RUN_DIR/stages/$MAP_STAGE/output.json"
if [[ ! -f "$MAP_MANIFEST" ]]; then
  echo "Example run failed: output.json missing for map stage $MAP_STAGE" >&2
  exit 1
fi

STAGE_META="$RUN_DIR/${MAP_STAGE}.meta.json"
if [[ ! -f "$STAGE_META" ]]; then
  echo "Example run failed: stage meta missing for $MAP_STAGE" >&2
  exit 1
fi

$PYTHON_BIN - <<PY
import json
from pathlib import Path

run_dir = Path("$RUN_DIR")
stage_meta = json.loads(Path("$STAGE_META").read_text())
if stage_meta.get("execution_mode") != "concurrent":
    raise SystemExit("Example run failed: execution_mode is not concurrent")
if stage_meta.get("max_in_flight") != 3:
    raise SystemExit("Example run failed: max_in_flight is not 3")

manifest = json.loads(Path("$MAP_MANIFEST").read_text())
items = manifest.get("items")
if not isinstance(items, list) or not items:
    raise SystemExit("Example run failed: map manifest items missing")
for entry in items:
    if entry.get("status") == "completed":
        output_path = entry.get("output_path")
        if not output_path or not (run_dir / output_path).exists():
            raise SystemExit("Example run failed: completed item missing output file")

output_dir = run_dir / "output"
if any(p.name == "raw.txt" for p in output_dir.rglob("raw.txt")):
    raise SystemExit("Example run failed: raw.txt leaked into output/")

print("Example run passed:", "$RUN_DIR")
PY
