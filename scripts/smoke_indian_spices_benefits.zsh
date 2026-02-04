#!/usr/bin/env zsh
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi


PIPELINE="pipelines/indian_spices_benefits.yaml"
LIST_STAGE="list_spices"
MAP_STAGE="spice_benefits"

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

LIST_JSON="$RUN_DIR/stages/$LIST_STAGE/output.json"
if [[ ! -f "$LIST_JSON" ]]; then
  echo "Smoke check failed: output.json missing for stage $LIST_STAGE" >&2
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
list_json = run_dir / "stages" / "$LIST_STAGE" / "output.json"
map_manifest = run_dir / "stages" / "$MAP_STAGE" / "output.json"

list_payload = json.loads(list_json.read_text())
items = list_payload.get("items")
if not isinstance(items, list):
    raise SystemExit("Smoke check failed: list stage output missing items list")
if len(items) != 5:
    raise SystemExit("Smoke check failed: list stage did not return 5 items")

manifest = json.loads(map_manifest.read_text())
manifest_items = manifest.get("items")
if not isinstance(manifest_items, list):
    raise SystemExit("Smoke check failed: map manifest items missing")

completed = 0
for entry in manifest_items:
    if entry.get("status") == "completed":
        completed += 1
        output_path = entry.get("output_path")
        if not output_path:
            raise SystemExit("Smoke check failed: completed item missing output_path")
        output_file = run_dir / output_path
        if not output_file.exists():
            raise SystemExit("Smoke check failed: item output file missing")
        if output_file.suffix != ".md":
            raise SystemExit("Smoke check failed: item output is not markdown")

if completed == 0:
    raise SystemExit("Smoke check failed: no completed map items")

print("Smoke check passed:", map_manifest)
PY
