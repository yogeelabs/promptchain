# PromptChain

Local-first, inspectable prompt chaining for deliberate multi-step workflows. Pipelines are YAML files in `pipelines/`, and every run writes a fully inspectable artifact directory under `runs/`.

## Purpose
- Compose multi-stage prompt workflows as simple YAML pipelines
- Keep runs reproducible and auditable with on-disk artifacts
- Support local models via Ollama with optional OpenAI stages

## Requirements
- Python 3
- Ollama running at `http://localhost:11434`
- Models specified in pipelines pulled in Ollama (e.g., `qwen3:8b`)

## Optional OpenAI Provider
PromptChain can optionally use the OpenAI API. This is opt-in and does not change the local-first default.

Requirements:
- `OPENAI_API_KEY` set in the environment (or `.env`; see `.env.example`)
- Pipeline or stage configured with `provider: openai`

## Setup

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quickstart (CLI)

Single stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/single.yaml --topic chess
```

Sequential chain:

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --topic chess
```

Fan-out map stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --topic chess
```

JSON → downstream stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/json_then_use.yaml
```

Per-stage file inputs:

```zsh
python -m promptchain.cli run --pipeline pipelines/file_inputs.yaml
```

Publish example:

```zsh
python -m promptchain.cli run --pipeline pipelines/publish_example.yaml --topic chess
```

## Example Scripts

Every pipeline in `pipelines/` has a matching sample script in `scripts/` named `run_<pipeline>.zsh`. These scripts run the pipeline with a small set of inputs and validate that core artifacts were produced.

Run a couple of examples:

```zsh
scripts/run_single.zsh
scripts/run_three_step.zsh
scripts/run_fanout_personas_jtbd.zsh
```

OpenAI examples require `OPENAI_API_KEY` (copy `.env.example` to `.env` and set it, or export the variable):

```zsh
scripts/run_openai_two_step.zsh
scripts/run_openai_concurrent_map.zsh
scripts/run_openai_batch_map.zsh
```

## Outputs

Each run creates a directory under `runs/<run_id>/` with:
- `run.json` metadata
- `logs/` raw model outputs
- `stages/<stage_id>/` outputs and artifacts
- `output/` published deliverables (if any)

## More Documentation

See `docs/README.md` for detailed usage, resume workflows, publishing behavior, and prompt context references.
