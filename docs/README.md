# PromptChain

Local-first, inspectable prompt chaining for deliberate multi-step workflows.

### Requirements
- Python 3
- Ollama running at `http://localhost:11434`
- Models specified in pipelines pulled in Ollama (e.g., `qwen3:8b`)

### Setup

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Quick smoke check:

```zsh
scripts/smoke_placeholder.zsh
```

### Run a single-stage pipeline (Phase 1)

```zsh
python -m promptchain.cli run --pipeline pipelines/single.yaml --topic chess
```

Notes:
- Requires Ollama running at `http://localhost:11434` with the model set in the pipeline.
- Outputs land under `runs/<run_id>/`.

### Run a sequential chain (Phase 2)

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --topic chess
```

Stop after a stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --topic chess --stop-after brainstorm
```

Resume from a stage using an existing run directory:

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --run-dir runs/<run_id> --from-stage expand
```

Run only a single stage:

```zsh
python -m promptchain.cli run --pipeline pipelines/three_step.yaml --topic chess --stage expand
```

### Run a JSON → downstream stage (Phase 3)

```zsh
python -m promptchain.cli run --pipeline pipelines/json_then_use.yaml
```

### Where outputs go

Each run creates: `runs/<run_id>/`

Per stage:
- `runs/<run_id>/stages/<stage_id>/raw.txt` — raw model output
- `runs/<run_id>/stages/<stage_id>/output.md` or `output.json` — stage output
- `runs/<run_id>/stages/<stage_id>/stage.json` — stage metadata, including rendered prompt
- `runs/<run_id>/stages/<stage_id>/context.json` — context details

Run metadata:
- `runs/<run_id>/run.json`

### Prompt context references

Prompt templates can reference upstream outputs:
- `{stage_outputs[stage_id]}` for upstream text
- `{stage_json[stage_id]}` for upstream JSON

`context.json` contains:
- `rendered_prompt`
- `context_all` (all available params + upstream outputs)
- `context_used` (only fields referenced in the prompt template)

### JSON outputs (Phase 3)

Stages with `output: json` must emit either:
- a JSON list (e.g., `["item A", "item B"]`), or
- a JSON object with `items` as a list.

PromptChain normalizes JSON outputs into:
```json
{
  "items": [
    { "id": "item_<hash>", "_selected": true, "value": "item A" }
  ]
}
```
`id` is deterministic based on item content, and `_selected` defaults to `true`.

### Smoke scripts

```zsh
scripts/smoke_placeholder.zsh
scripts/smoke_three_step.zsh
scripts/smoke_json_list.zsh
```
