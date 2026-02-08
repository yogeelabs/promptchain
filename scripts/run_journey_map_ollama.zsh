#!/usr/bin/env zsh
set -euo pipefail

source .venv/bin/activate

python -m promptchain.cli run \
  --pipeline pipelines/journey_map_ollama.yaml \
  --product "Youtube Cooking Videos" \
  --industry "Cooking Videos Content Industry" \
  --persona "Person looking to cook by learning watching from youtube cooking video"
