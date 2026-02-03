# PromptChain

Local-first, inspectable prompt chaining for deliberate multi-step workflows.

## Quickstart

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
scripts/smoke_placeholder.zsh
```

## Run a Single Pipeline (Phase 1)

```zsh
python -m promptchain.cli run --pipeline pipelines/single.yaml --topic chess
```

Notes:
- Requires Ollama running at http://localhost:11434 with the model set in the pipeline.
- Outputs land under `runs/<run_id>/`.
