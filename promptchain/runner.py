from __future__ import annotations

import json
from dataclasses import asdict
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


class Runner:
    def __init__(self, runs_root: Path | str = "runs") -> None:
        self.runs_root = Path(runs_root)
        self.provider = OllamaProvider()

    def run(self, pipeline: Pipeline, params: Mapping[str, Any]) -> Path:
        if len(pipeline.stages) != 1:
            raise RunnerError("Phase 1 supports exactly one stage per pipeline.")

        self.runs_root.mkdir(parents=True, exist_ok=True)
        run_id = _new_run_id()
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        meta = {
            "run_id": run_id,
            "pipeline": pipeline.name,
            "pipeline_model": pipeline.model,
            "params": dict(params),
            "started_at": _utc_now(),
            "status": "started",
        }
        _write_json(run_dir / "run.json", meta)

        try:
            stage = pipeline.stages[0]
            stage_dir = run_dir / "stages" / stage.stage_id
            stage_dir.mkdir(parents=True, exist_ok=True)

            rendered_prompt = _render_prompt(stage.prompt, params)
            stage_meta = {
                "stage_id": stage.stage_id,
                "model": stage.model,
                "output": stage.output,
                "prompt": rendered_prompt,
                "started_at": _utc_now(),
            }
            _write_json(stage_dir / "stage.json", stage_meta)

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
                    raise RunnerError("Stage output was not valid JSON.") from exc
                _write_json(stage_dir / "output.json", parsed)
            else:
                (stage_dir / "output.md").write_text(response_text)

            stage_meta["completed_at"] = _utc_now()
            _write_json(stage_dir / "stage.json", stage_meta)

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
