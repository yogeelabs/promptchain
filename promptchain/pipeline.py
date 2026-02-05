from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Stage:
    stage_id: str
    prompt: str
    provider: str
    model: str
    reasoning_effort: str | None
    temperature: float | None
    enabled: bool
    concurrency_enabled: bool
    concurrency_max_in_flight: int | None
    output: str  # "markdown" or "json"
    mode: str  # "single" or "map"
    map_from: str | None
    map_from_file: str | None
    publish: bool
    input_files: dict[str, "InputFile"]


@dataclass
class InputFile:
    name: str
    path: str
    kind: str  # "text" or "json"


@dataclass
class Pipeline:
    name: str
    provider: str
    model: str
    reasoning_effort: str | None
    temperature: float | None
    stages: list[Stage]
    path: str


class PipelineError(RuntimeError):
    pass


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"Field '{field}' must be a non-empty string.")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PipelineError(f"Field '{field}' must be a boolean.")
    return value


def _require_provider(value: Any, field: str) -> str:
    provider = _require_str(value, field).lower()
    if provider not in {"ollama", "openai"}:
        raise PipelineError(
            f"Field '{field}' must be 'ollama' or 'openai', got '{provider}'."
        )
    return provider


def _require_reasoning_effort(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"Field '{field}' must be a non-empty string.")
    reasoning = value.strip().lower()
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    if reasoning not in allowed:
        raise PipelineError(
            f"Field '{field}' must be one of {sorted(allowed)}, got '{value}'."
        )
    return reasoning


def _require_temperature(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise PipelineError(f"Field '{field}' must be a number.")
    return float(value)


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError(f"Field '{field}' must be a mapping.")
    return value


def _require_int(value: Any, field: str) -> int:
    if not isinstance(value, int):
        raise PipelineError(f"Field '{field}' must be an integer.")
    return value


def _parse_input_file(name: str, value: Any, field: str) -> InputFile:
    if isinstance(value, str):
        path = value
        kind = "json" if path.lower().endswith(".json") else "text"
        return InputFile(name=name, path=path, kind=kind)
    if isinstance(value, dict):
        raw_path = value.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PipelineError(f"Field '{field}.path' must be a non-empty string.")
        raw_kind = value.get("type", "json" if raw_path.lower().endswith(".json") else "text")
        if not isinstance(raw_kind, str) or raw_kind.lower() not in {"text", "json"}:
            raise PipelineError(
                f"Field '{field}.type' must be 'text' or 'json', got '{raw_kind}'."
            )
        return InputFile(name=name, path=raw_path, kind=raw_kind.lower())
    raise PipelineError(f"Field '{field}' must be a string path or mapping.")


def load_pipeline(path: str | Path) -> Pipeline:
    path = Path(path)
    if not path.exists():
        raise PipelineError(f"Pipeline file not found: {path}")

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise PipelineError("Pipeline YAML must be a mapping.")

    name = _require_str(data.get("name", path.stem), "name")
    provider = _require_provider(data.get("provider", "ollama"), "provider")
    model = _require_str(data.get("model", ""), "model")
    reasoning_effort = _require_reasoning_effort(
        data.get("reasoning_effort", data.get("reasoning")),
        "reasoning_effort",
    )
    temperature = _require_temperature(data.get("temperature"), "temperature")

    stages_raw = data.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise PipelineError("Pipeline must include a non-empty 'stages' list.")

    stages: list[Stage] = []
    for idx, stage_raw in enumerate(stages_raw, start=1):
        if not isinstance(stage_raw, dict):
            raise PipelineError(f"Stage {idx} must be a mapping.")
        stage_id = _require_str(stage_raw.get("id", f"stage_{idx}"), "stages.id")
        prompt = _require_str(stage_raw.get("prompt", ""), f"stages[{stage_id}].prompt")
        stage_provider = stage_raw.get("provider", provider)
        stage_provider = _require_provider(stage_provider, f"stages[{stage_id}].provider")
        stage_model = stage_raw.get("model", model)
        stage_model = _require_str(stage_model, f"stages[{stage_id}].model")
        stage_reasoning_effort = _require_reasoning_effort(
            stage_raw.get(
                "reasoning_effort",
                stage_raw.get("reasoning", reasoning_effort),
            ),
            f"stages[{stage_id}].reasoning_effort",
        )
        stage_temperature = _require_temperature(
            stage_raw.get("temperature", temperature),
            f"stages[{stage_id}].temperature",
        )
        enabled = stage_raw.get("enabled", True)
        enabled = _require_bool(enabled, f"stages[{stage_id}].enabled")
        output = stage_raw.get("output", "markdown")
        output = _require_str(output, f"stages[{stage_id}].output").lower()
        if output not in {"markdown", "json"}:
            raise PipelineError(
                f"Stage '{stage_id}' output must be 'markdown' or 'json', got '{output}'."
            )
        mode = stage_raw.get("mode", "single")
        mode = _require_str(mode, f"stages[{stage_id}].mode").lower()
        if mode not in {"single", "map"}:
            raise PipelineError(
                f"Stage '{stage_id}' mode must be 'single' or 'map', got '{mode}'."
            )
        concurrency_enabled = False
        concurrency_max_in_flight: int | None = None
        concurrency_raw = stage_raw.get("concurrency")
        if concurrency_raw is not None:
            if mode != "map":
                raise PipelineError(
                    f"Stage '{stage_id}' concurrency is only valid for map stages."
                )
            concurrency_cfg = _require_mapping(
                concurrency_raw, f"stages[{stage_id}].concurrency"
            )
            concurrency_enabled = _require_bool(
                concurrency_cfg.get("enabled", False),
                f"stages[{stage_id}].concurrency.enabled",
            )
            max_in_flight_raw = concurrency_cfg.get("max_in_flight")
            if max_in_flight_raw is not None:
                max_in_flight = _require_int(
                    max_in_flight_raw, f"stages[{stage_id}].concurrency.max_in_flight"
                )
                if max_in_flight < 1:
                    raise PipelineError(
                        f"Field 'stages[{stage_id}].concurrency.max_in_flight' must be >= 1."
                    )
                concurrency_max_in_flight = max_in_flight
        map_from = stage_raw.get("map_from")
        map_from_file = stage_raw.get("map_from_file")
        if mode == "map":
            if map_from and map_from_file:
                raise PipelineError(
                    f"Stage '{stage_id}' cannot set both map_from and map_from_file."
                )
            if map_from_file is not None:
                map_from_file = _require_str(
                    map_from_file, f"stages[{stage_id}].map_from_file"
                )
                map_from = None
            else:
                map_from = _require_str(map_from, f"stages[{stage_id}].map_from")
        elif map_from is not None:
            raise PipelineError(
                f"Stage '{stage_id}' cannot set map_from unless mode is 'map'."
            )
        elif map_from_file is not None:
            raise PipelineError(
                f"Stage '{stage_id}' cannot set map_from_file unless mode is 'map'."
            )

        input_files: dict[str, InputFile] = {}
        inputs_raw = stage_raw.get("inputs")
        if inputs_raw is not None:
            inputs = _require_mapping(inputs_raw, f"stages[{stage_id}].inputs")
            files_raw = inputs.get("files")
            if files_raw is None:
                files_raw = {}
            files = _require_mapping(files_raw, f"stages[{stage_id}].inputs.files")
            for name, value in files.items():
                if not isinstance(name, str) or not name.strip():
                    raise PipelineError(
                        f"Field 'stages[{stage_id}].inputs.files' keys must be non-empty strings."
                    )
                input_files[name] = _parse_input_file(
                    name, value, f"stages[{stage_id}].inputs.files.{name}"
                )

        publish = stage_raw.get("publish", False)
        publish = _require_bool(publish, f"stages[{stage_id}].publish")
        stages.append(
            Stage(
                stage_id=stage_id,
                prompt=prompt,
                provider=stage_provider,
                model=stage_model,
                reasoning_effort=stage_reasoning_effort,
                temperature=stage_temperature,
                enabled=enabled,
                concurrency_enabled=concurrency_enabled,
                concurrency_max_in_flight=concurrency_max_in_flight,
                output=output,
                mode=mode,
                map_from=map_from,
                map_from_file=map_from_file,
                publish=publish,
                input_files=input_files,
            )
        )

    return Pipeline(
        name=name,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        stages=stages,
        path=str(path),
    )
