from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Stage:
    stage_id: str
    prompt: str
    model: str
    output: str  # "markdown" or "json"


@dataclass
class Pipeline:
    name: str
    model: str
    stages: list[Stage]
    path: str


class PipelineError(RuntimeError):
    pass


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"Field '{field}' must be a non-empty string.")
    return value


def load_pipeline(path: str | Path) -> Pipeline:
    path = Path(path)
    if not path.exists():
        raise PipelineError(f"Pipeline file not found: {path}")

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise PipelineError("Pipeline YAML must be a mapping.")

    name = _require_str(data.get("name", path.stem), "name")
    model = _require_str(data.get("model", ""), "model")

    stages_raw = data.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise PipelineError("Pipeline must include a non-empty 'stages' list.")

    stages: list[Stage] = []
    for idx, stage_raw in enumerate(stages_raw, start=1):
        if not isinstance(stage_raw, dict):
            raise PipelineError(f"Stage {idx} must be a mapping.")
        stage_id = _require_str(stage_raw.get("id", f"stage_{idx}"), "stages.id")
        prompt = _require_str(stage_raw.get("prompt", ""), f"stages[{stage_id}].prompt")
        stage_model = stage_raw.get("model", model)
        stage_model = _require_str(stage_model, f"stages[{stage_id}].model")
        output = stage_raw.get("output", "markdown")
        output = _require_str(output, f"stages[{stage_id}].output").lower()
        if output not in {"markdown", "json"}:
            raise PipelineError(
                f"Stage '{stage_id}' output must be 'markdown' or 'json', got '{output}'."
            )
        stages.append(Stage(stage_id=stage_id, prompt=prompt, model=stage_model, output=output))

    return Pipeline(name=name, model=model, stages=stages, path=str(path))
