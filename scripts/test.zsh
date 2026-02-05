#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Running Ollama smoke..."
"$SCRIPT_DIR/smoke_placeholder.zsh"
echo "Running disabled stage smoke..."
"$SCRIPT_DIR/smoke_disabled_stage.zsh"
echo "Running disabled dependency smoke..."
"$SCRIPT_DIR/smoke_disabled_dependency.zsh"

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "Running OpenAI smoke..."
  "$SCRIPT_DIR/smoke_openai_two_step.zsh"
  echo "Running OpenAI concurrent map smoke..."
  "$SCRIPT_DIR/smoke_openai_concurrent_map.zsh"
  echo "Running OpenAI batch map smoke..."
  "$SCRIPT_DIR/smoke_openai_batch_map.zsh"
else
  echo "Skipping OpenAI smoke: OPENAI_API_KEY is not set" >&2
fi
