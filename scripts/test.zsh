#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Running Ollama smoke..."
"$SCRIPT_DIR/smoke_placeholder.zsh"

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "Running OpenAI smoke..."
  "$SCRIPT_DIR/smoke_openai_two_step.zsh"
else
  echo "Skipping OpenAI smoke: OPENAI_API_KEY is not set" >&2
fi
