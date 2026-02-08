#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Running local examples..."
"$SCRIPT_DIR/run_single.zsh"
echo "Running disabled stage example..."
"$SCRIPT_DIR/run_disabled_stage_example.zsh"
echo "Running disabled dependency example..."
"$SCRIPT_DIR/run_disabled_dependency_example.zsh"

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "Running OpenAI examples..."
  "$SCRIPT_DIR/run_openai_two_step.zsh"
  echo "Running OpenAI concurrent map example..."
  "$SCRIPT_DIR/run_openai_concurrent_map.zsh"
  echo "Running OpenAI batch map example..."
  "$SCRIPT_DIR/run_openai_batch_map.zsh"
else
  echo "Skipping OpenAI examples: OPENAI_API_KEY is not set" >&2
fi
