from __future__ import annotations

import json
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from promptchain.pipeline import Pipeline, Stage
from promptchain.providers.ollama import OllamaProvider


class RunnerError(RuntimeError):
    pass


def _render_prompt(prompt: str, params: Mapping[str, Any]) -> str:
    try:
        return prompt.format_map(params)
    except KeyError as exc:
        missing = exc.args[0]
        raise RunnerError(f"Missing required parameter: {missing}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{uuid4().hex[:8]}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RunnerError(f"{label} contained invalid JSON: {path}") from exc


def _stage_output_paths(stage: Stage, stage_dir: Path) -> tuple[Path, Path]:
    output_path = stage_dir / ("output.json" if stage.output == "json" else "output.md")
    raw_path = stage_dir / "raw.txt"
    return output_path, raw_path


def _load_stage_output(stage: Stage, stage_dir: Path) -> tuple[str, Any | None]:
    output_path, _ = _stage_output_paths(stage, stage_dir)
    if not output_path.exists():
        raise RunnerError(f"Missing output for stage '{stage.stage_id}' at {output_path}")
    if stage.output == "json":
        parsed = _read_json(output_path, f"Stage '{stage.stage_id}' output")
        rendered = json.dumps(parsed, indent=2, ensure_ascii=True)
        return rendered, parsed
    return output_path.read_text(), None


def _stage_completed(stage_dir: Path) -> bool:
    stage_meta_path = stage_dir / "stage.json"
    if not stage_meta_path.exists():
        return False
    meta = _read_json(stage_meta_path, "Stage metadata")
    return meta.get("status") == "completed"


def _extract_template_fields(template: str) -> list[str]:
    fields: list[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if field_name:
            fields.append(field_name)
    return fields


def _build_used_context(
    template_fields: list[str],
    params: Mapping[str, Any],
    stage_outputs: Mapping[str, str],
    stage_json: Mapping[str, Any],
) -> dict[str, Any]:
    params_used: dict[str, Any] = {}
    stage_outputs_used: dict[str, str] = {}
    stage_json_used: dict[str, Any] = {}
    raw_fields: list[str] = []

    for field in template_fields:
        raw_fields.append(field)
        if field.startswith("stage_outputs[") and field.endswith("]"):
            key = field[len("stage_outputs[") : -1]
            if key in stage_outputs:
                stage_outputs_used[key] = stage_outputs[key]
            continue
        if field.startswith("stage_json[") and field.endswith("]"):
            key = field[len("stage_json[") : -1]
            if key in stage_json:
                stage_json_used[key] = stage_json[key]
            continue
        if field in params:
            params_used[field] = params[field]

    return {
        "params": params_used,
        "stage_outputs": stage_outputs_used,
        "stage_json": stage_json_used,
        "template_fields": raw_fields,
    }


def _resolve_stage_index(stage_ids: list[str], stage_id: str, label: str) -> int:
    if stage_id not in stage_ids:
        raise RunnerError(f"{label} stage not found: {stage_id}")
    return stage_ids.index(stage_id)


class Runner:
    def __init__(self, runs_root: Path | str = "runs") -> None:
        self.runs_root = Path(runs_root)
        self.provider = OllamaProvider()

    def run(
        self,
        pipeline: Pipeline,
        params: Mapping[str, Any],
        *,
        run_dir: Path | str | None = None,
        start_stage: str | None = None,
        stop_after: str | None = None,
        stage_only: str | None = None,
    ) -> Path:
        stage_ids = [stage.stage_id for stage in pipeline.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise RunnerError("Stage ids must be unique.")

        if stage_only and (start_stage or stop_after):
            raise RunnerError("Use --stage without --from-stage or --stop-after.")

        if stage_only:
            start_stage = stage_only
            stop_after = stage_only

        if start_stage is None:
            start_stage = stage_ids[0]
        if stop_after is None:
            stop_after = stage_ids[-1]

        start_idx = _resolve_stage_index(stage_ids, start_stage, "Start")
        stop_idx = _resolve_stage_index(stage_ids, stop_after, "Stop-after")
        if start_idx > stop_idx:
            raise RunnerError("Start stage must come before stop-after stage.")

        if run_dir is None:
            self.runs_root.mkdir(parents=True, exist_ok=True)
            run_id = _new_run_id()
            run_dir = self.runs_root / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            meta = {
                "run_id": run_id,
                "pipeline": pipeline.name,
                "pipeline_model": pipeline.model,
                "pipeline_path": str(getattr(pipeline, "path", "")),
                "params": dict(params),
                "started_at": _utc_now(),
                "status": "started",
                "stages": {},
            }
            _write_json(run_dir / "run.json", meta)
        else:
            run_dir = Path(run_dir)
            run_meta_path = run_dir / "run.json"
            if not run_meta_path.exists():
                raise RunnerError(f"Run metadata not found in {run_dir}")
            meta = _read_json(run_meta_path, "Run metadata")
            params = meta.get("params", {})
            if meta.get("pipeline") != pipeline.name:
                raise RunnerError("Pipeline name does not match existing run.")
            meta.setdefault("stages", {})

        for stage in pipeline.stages[:start_idx]:
            stage_dir = run_dir / "stages" / stage.stage_id
            if not _stage_completed(stage_dir):
                raise RunnerError(
                    f"Cannot start at '{stage_ids[start_idx]}': "
                    f"upstream stage '{stage.stage_id}' is incomplete."
                )

        try:
            for idx, stage in enumerate(pipeline.stages):
                if idx < start_idx or idx > stop_idx:
                    continue

                stage_dir = run_dir / "stages" / stage.stage_id
                stage_dir.mkdir(parents=True, exist_ok=True)

                if _stage_completed(stage_dir):
                    continue

                context = dict(params)
                stage_outputs: dict[str, str] = {}
                stage_json: dict[str, Any] = {}
                for prior in pipeline.stages[:idx]:
                    prior_dir = run_dir / "stages" / prior.stage_id
                    output_text, output_json = _load_stage_output(prior, prior_dir)
                    stage_outputs[prior.stage_id] = output_text
                    if output_json is not None:
                        stage_json[prior.stage_id] = output_json
                context["stage_outputs"] = stage_outputs
                context["stage_json"] = stage_json

                template_fields = _extract_template_fields(stage.prompt)
                used_context = _build_used_context(
                    template_fields=template_fields,
                    params=params,
                    stage_outputs=stage_outputs,
                    stage_json=stage_json,
                )
                rendered_prompt = _render_prompt(stage.prompt, context)
                stage_meta = {
                    "stage_id": stage.stage_id,
                    "model": stage.model,
                    "output": stage.output,
                    "prompt": rendered_prompt,
                    "started_at": _utc_now(),
                    "status": "started",
                }
                _write_json(stage_dir / "stage.json", stage_meta)
                _write_json(
                    stage_dir / "context.json",
                    {
                        "rendered_prompt": rendered_prompt,
                        "context_all": {
                            "params": dict(params),
                            "stage_outputs": stage_outputs,
                            "stage_json": stage_json,
                        },
                        "context_used": used_context,
                    },
                )
                meta["stages"][stage.stage_id] = {
                    "status": "started",
                    "started_at": stage_meta["started_at"],
                }
                _write_json(run_dir / "run.json", meta)

                response_text = self.provider.generate(model=stage.model, prompt=rendered_prompt)
                (stage_dir / "raw.txt").write_text(response_text)

                if stage.output == "json":
                    try:
                        parsed = json.loads(response_text)
                    except json.JSONDecodeError as exc:
                        error = {
                            "error": "Invalid JSON output.",
                            "detail": str(exc),
                        }
                        _write_json(stage_dir / "error.json", error)
                        stage_meta["status"] = "failed"
                        stage_meta["failed_at"] = _utc_now()
                        _write_json(stage_dir / "stage.json", stage_meta)
                        meta["stages"][stage.stage_id] = {
                            "status": "failed",
                            "failed_at": stage_meta["failed_at"],
                            "error": "Stage output was not valid JSON.",
                        }
                        meta["status"] = "failed"
                        meta["error"] = f"Stage '{stage.stage_id}' output was not valid JSON."
                        meta["failed_at"] = _utc_now()
                        _write_json(run_dir / "run.json", meta)
                        raise RunnerError("Stage output was not valid JSON.") from exc
                    _write_json(stage_dir / "output.json", parsed)
                else:
                    (stage_dir / "output.md").write_text(response_text)

                stage_meta["completed_at"] = _utc_now()
                stage_meta["status"] = "completed"
                _write_json(stage_dir / "stage.json", stage_meta)
                meta["stages"][stage.stage_id] = {
                    "status": "completed",
                    "completed_at": stage_meta["completed_at"],
                }
                _write_json(run_dir / "run.json", meta)

                if idx == stop_idx:
                    if stop_idx == len(pipeline.stages) - 1:
                        meta["completed_at"] = _utc_now()
                        meta["status"] = "completed"
                    else:
                        meta["stopped_at"] = _utc_now()
                        meta["status"] = "stopped"
                    _write_json(run_dir / "run.json", meta)
                    return run_dir

            meta["completed_at"] = _utc_now()
            meta["status"] = "completed"
            _write_json(run_dir / "run.json", meta)
        except Exception as exc:
            meta["status"] = "failed"
            meta["error"] = str(exc)
            meta["failed_at"] = _utc_now()
            _write_json(run_dir / "run.json", meta)
            raise

        return run_dir
