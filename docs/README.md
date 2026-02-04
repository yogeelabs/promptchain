# PromptChain

Local-first, inspectable prompt chaining for deliberate multi-step workflows.

### Requirements
- Python 3
- Ollama running at `http://localhost:11434`
- Models specified in pipelines pulled in Ollama (e.g., `qwen3:8b`)

### Optional OpenAI Provider (Phase 9)

PromptChain can optionally use the OpenAI API. This is opt-in and does not change the local-first default.

Requirements:
- `OPENAI_API_KEY` set in the environment
- Pipeline configured with `provider: openai`

Example:
```yaml
name: openai_example
provider: openai
model: <openai-model-id>
stages:
  - id: draft
    prompt: "Draft a short summary of {topic}."
    output: markdown
```

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

### Run a fan-out map stage (Phase 4)

```zsh
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --topic chess
```

### Human-in-the-loop editing & resume (Phase 5)

Pause after a stage, edit outputs, then resume downstream without recomputation:

```zsh
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --topic chess --stop-after personas
# edit runs/<run_id>/stages/personas/output.json
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --run-dir runs/<run_id> --from-stage jtbd
```

Notes:
- Resume never overwrites existing `output.*` artifacts. To recompute a stage or item, delete its output file (or the whole stage/item directory) first.
- For list outputs, you can prune items or set `_selected: false` to skip fan-out items.
- If you manually fix or create an `output.*` file for a failed stage/item, resume will treat it as completed.

### Per-stage model selection (Phase 6)

Set a pipeline default `model`, and override per stage as needed:

```yaml
name: mixed_models
model: qwen3:8b
stages:
  - id: brainstorm
    prompt: "List five angles for {topic}."
    output: markdown
  - id: refine
    model: llama3.1:70b
    prompt: "Refine these angles into a tight brief:\n\n{stage_outputs[brainstorm]}"
    output: markdown
```

You can also set a pipeline default `provider` and override per stage:
```yaml
name: mixed_providers
provider: ollama
model: qwen3:8b
stages:
  - id: local
    prompt: "List five angles for {topic}."
    output: markdown
  - id: external
    provider: openai
    model: <openai-model-id>
    prompt: "Refine these angles into a tight brief:\n\n{stage_outputs[local]}"
    output: markdown
```

If a model is not available in Ollama, the run fails fast with a clear error listing available models.

### Where outputs go

Each run creates: `runs/<run_id>/`

Final deliverables are published to:
- `runs/<run_id>/output/`

Publishing rules:
- If any stage sets `publish: true`, only those stages are published.
- If no stage sets `publish: true`, the last stage is published by default.

Example:
```yaml
stages:
  - id: draft
    prompt: "Draft a short summary of {topic}."
    output: markdown
    publish: true
```

Run the example pipeline:
```zsh
python -m promptchain.cli run --pipeline pipelines/publish_example.yaml --topic chess
```

Per stage:
- `runs/<run_id>/stages/<stage_id>/raw.txt` — raw model output
- `runs/<run_id>/stages/<stage_id>/output.md` or `output.json` — stage output
- `runs/<run_id>/stages/<stage_id>/stage.json` — stage metadata, including rendered prompt
- `runs/<run_id>/stages/<stage_id>/context.json` — context details

Map stage items:
- `runs/<run_id>/stages/<stage_id>/items/<item_id>/raw.txt`
- `runs/<run_id>/stages/<stage_id>/items/<item_id>/output.md` or `output.json`
- `runs/<run_id>/stages/<stage_id>/items/<item_id>/stage.json`
- `runs/<run_id>/stages/<stage_id>/items/<item_id>/context.json`
- `runs/<run_id>/stages/<stage_id>/output.json` — manifest of per-item outputs

Published outputs (examples):
- `runs/<run_id>/output/<stage_id>/output.md` or `output.json`
- `runs/<run_id>/output/<stage_id>/<item_id>/output.md` or `output.json` (map stages)

Run metadata:
- `runs/<run_id>/run.json`
- `runs/<run_id>/run.log` — timestamped stage-level events and errors

### Prompt context references

Prompt templates can reference upstream outputs:
- `{stage_outputs[stage_id]}` for upstream text
- `{stage_json[stage_id]}` for upstream JSON

Map-stage prompt templates can also reference:
- `{item[...]}` for the current item (e.g., `{item[value]}`)
- `{item_index}` and `{item_id}`

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
scripts/smoke_fanout_personas.zsh
scripts/smoke_three_stage_fanout_classify.zsh
scripts/smoke_three_stage_fanout_classify_per_item.zsh
scripts/smoke_indian_spices_benefits.zsh
scripts/smoke_mixed_models.zsh
```
