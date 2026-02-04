# PromptChain

Local-first, inspectable prompt chaining for deliberate multi-step workflows.

## Requirements
- Python 3
- Ollama running at `http://localhost:11434`
- Models specified in pipelines pulled in Ollama (e.g., `qwen3:8b`)

## Optional OpenAI Provider (Phase 9)

PromptChain can optionally use the OpenAI API. This is opt-in and does not change the local-first default.

Requirements:
- `OPENAI_API_KEY` set in the environment
- Pipeline configured with `provider: openai`

## Setup

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quickstart

Run a single-stage pipeline:

```zsh
python -m promptchain.cli run --pipeline pipelines/single.yaml --topic chess
```

Run a sequential chain:

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --topic chess
```

Run a fan-out map stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --topic chess
```

Run a map stage from a text list file:

```zsh
python -m promptchain.cli run --pipeline pipelines/text_list_fanout.yaml
```

Run the publish example:

```zsh
python -m promptchain.cli run --pipeline pipelines/publish_example.yaml --topic chess
```

## Smoke Scripts

```zsh
scripts/smoke_placeholder.zsh
scripts/smoke_three_step.zsh
scripts/smoke_json_list.zsh
scripts/smoke_fanout_personas.zsh
scripts/smoke_three_stage_fanout_classify.zsh
scripts/smoke_three_stage_fanout_classify_per_item.zsh
scripts/smoke_indian_spices_benefits.zsh
scripts/smoke_mixed_models.zsh
scripts/smoke_openai_two_step.zsh
scripts/smoke_text_list_fanout.zsh
scripts/smoke_json_list_fanout.zsh
```

## More Documentation

See `docs/README.md` for detailed usage, resume workflows, publishing behavior, and prompt context references.
