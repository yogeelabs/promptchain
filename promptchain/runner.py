from __future__ import annotations

import hashlib
import json
import shutil
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


def _append_log(run_dir: Path, message: str) -> None:
    timestamp = _utc_now()
    log_path = run_dir / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RunnerError(f"{label} contained invalid JSON: {path}") from exc


def _stable_item_id(payload: Mapping[str, Any]) -> str:
    content = {key: payload[key] for key in sorted(payload) if key not in {"id", "_selected"}}
    encoded = json.dumps(content, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:10]
    return f"item_{digest}"


def _normalize_json_output(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "items" in payload:
        items = payload["items"]
    else:
        items = payload

    if not isinstance(items, list):
        raise RunnerError("JSON output must be a list or an object with an 'items' list.")

    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized_item = dict(item)
        else:
            normalized_item = {"value": item}
        if "id" not in normalized_item:
            normalized_item["id"] = _stable_item_id(normalized_item)
        if "_selected" not in normalized_item:
            normalized_item["_selected"] = True
        normalized.append(normalized_item)

    return {"items": normalized}


def _stage_output_paths(stage: Stage, stage_dir: Path) -> tuple[Path, Path]:
    if stage.mode == "map":
        output_path = stage_dir / "output.json"
    else:
        output_path = stage_dir / ("output.json" if stage.output == "json" else "output.md")
    raw_path = stage_dir / "raw.txt"
    return output_path, raw_path


def _load_stage_output(stage: Stage, stage_dir: Path) -> tuple[str, Any | None]:
    output_path, _ = _stage_output_paths(stage, stage_dir)
    if not output_path.exists():
        raise RunnerError(f"Missing output for stage '{stage.stage_id}' at {output_path}")
    if stage.mode == "map" or stage.output == "json":
        parsed = _read_json(output_path, f"Stage '{stage.stage_id}' output")
        rendered = json.dumps(parsed, indent=2, ensure_ascii=True)
        return rendered, parsed
    return output_path.read_text(), None


def _stage_output_path(stage: Stage, stage_dir: Path) -> Path:
    output_path, _ = _stage_output_paths(stage, stage_dir)
    return output_path


def _stage_output_exists(stage: Stage, stage_dir: Path) -> bool:
    return _stage_output_path(stage, stage_dir).exists()


def _item_output_path(stage: Stage, item_dir: Path) -> Path:
    return item_dir / ("output.json" if stage.output == "json" else "output.md")


def _item_output_exists(stage: Stage, item_dir: Path) -> bool:
    return _item_output_path(stage, item_dir).exists()


def _stage_completed(stage: Stage, stage_dir: Path) -> bool:
    return _stage_output_exists(stage, stage_dir)


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
    item: Mapping[str, Any] | None = None,
    item_index: int | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    params_used: dict[str, Any] = {}
    stage_outputs_used: dict[str, str] = {}
    stage_json_used: dict[str, Any] = {}
    item_used: Mapping[str, Any] | None = None
    item_index_used: int | None = None
    item_id_used: str | None = None
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
        if field.startswith("item[") and field.endswith("]"):
            if item is not None:
                item_used = item
            continue
        if field == "item":
            if item is not None:
                item_used = item
            continue
        if field == "item_index" and item_index is not None:
            item_index_used = item_index
            continue
        if field == "item_id" and item_id is not None:
            item_id_used = item_id
            continue
        if field in params:
            params_used[field] = params[field]

    context_used: dict[str, Any] = {
        "params": params_used,
        "stage_outputs": stage_outputs_used,
        "stage_json": stage_json_used,
        "template_fields": raw_fields,
    }
    if item_used is not None:
        context_used["item"] = item_used
    if item_index_used is not None:
        context_used["item_index"] = item_index_used
    if item_id_used is not None:
        context_used["item_id"] = item_id_used
    return context_used


def _resolve_stage_index(stage_ids: list[str], stage_id: str, label: str) -> int:
    if stage_id not in stage_ids:
        raise RunnerError(f"{label} stage not found: {stage_id}")
    return stage_ids.index(stage_id)


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _stage_publish_enabled(pipeline: Pipeline) -> list[Stage]:
    publish_stages = [stage for stage in pipeline.stages if stage.publish]
    if publish_stages:
        return publish_stages
    return [pipeline.stages[-1]]


class Runner:
    def __init__(self, runs_root: Path | str = "runs") -> None:
        self.runs_root = Path(runs_root)
        self.provider = OllamaProvider()

    def _gather_stage_context(
        self,
        pipeline: Pipeline,
        stage_index: int,
        run_dir: Path,
        params: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
        stage_outputs: dict[str, str] = {}
        stage_json: dict[str, Any] = {}
        for prior in pipeline.stages[:stage_index]:
            prior_dir = run_dir / "stages" / prior.stage_id
            output_text, output_json = _load_stage_output(prior, prior_dir)
            stage_outputs[prior.stage_id] = output_text
            if output_json is not None:
                stage_json[prior.stage_id] = output_json
        context = dict(params)
        context["stage_outputs"] = stage_outputs
        context["stage_json"] = stage_json
        return context, stage_outputs, stage_json

    def _run_single_stage(
        self,
        *,
        pipeline: Pipeline,
        stage: Stage,
        stage_index: int,
        run_dir: Path,
        params: Mapping[str, Any],
        meta: dict[str, Any],
    ) -> None:
        stage_dir = run_dir / "stages" / stage.stage_id
        stage_dir.mkdir(parents=True, exist_ok=True)

        if _stage_completed(stage, stage_dir):
            return

        context, stage_outputs, stage_json = self._gather_stage_context(
            pipeline, stage_index, run_dir, params
        )

        self.provider.ensure_model(stage.model)

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
            "mode": stage.mode,
            "publish": stage.publish,
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
        _append_log(run_dir, f"stage:{stage.stage_id} status=started mode={stage.mode}")

        response_text = self.provider.generate(model=stage.model, prompt=rendered_prompt)
        (stage_dir / "raw.txt").write_text(response_text)

        if stage.output == "json":
            try:
                parsed = json.loads(response_text)
                normalized = _normalize_json_output(parsed)
            except (json.JSONDecodeError, RunnerError) as exc:
                error_message = "Stage output was not valid JSON list."
                error = {
                    "stage_id": stage.stage_id,
                    "error": "Invalid JSON output format.",
                    "detail": str(exc),
                }
                _write_json(stage_dir / "error.json", error)
                stage_meta["status"] = "failed"
                stage_meta["failed_at"] = _utc_now()
                _write_json(stage_dir / "stage.json", stage_meta)
                meta["stages"][stage.stage_id] = {
                    "status": "failed",
                    "failed_at": stage_meta["failed_at"],
                    "error": error_message,
                }
                meta["status"] = "failed"
                meta["error"] = f"Stage '{stage.stage_id}' output was not valid JSON list."
                meta["failed_at"] = _utc_now()
                _write_json(run_dir / "run.json", meta)
                _append_log(
                    run_dir,
                    f"stage:{stage.stage_id} status=failed error=invalid_json_output",
                )
                raise RunnerError(error_message) from exc
            _write_json(stage_dir / "output.json", normalized)
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
        _append_log(run_dir, f"stage:{stage.stage_id} status=completed")

    def _run_map_stage(
        self,
        *,
        pipeline: Pipeline,
        stage: Stage,
        stage_index: int,
        run_dir: Path,
        params: Mapping[str, Any],
        meta: dict[str, Any],
    ) -> None:
        stage_dir = run_dir / "stages" / stage.stage_id
        stage_dir.mkdir(parents=True, exist_ok=True)

        if _stage_completed(stage, stage_dir):
            return

        if not stage.map_from:
            raise RunnerError(f"Map stage '{stage.stage_id}' is missing map_from.")

        map_from = stage.map_from
        if map_from not in [s.stage_id for s in pipeline.stages]:
            raise RunnerError(f"Map stage '{stage.stage_id}' references unknown stage '{map_from}'.")

        if map_from not in [s.stage_id for s in pipeline.stages[:stage_index]]:
            raise RunnerError(
                f"Map stage '{stage.stage_id}' must reference an upstream stage."
            )

        context, stage_outputs, stage_json = self._gather_stage_context(
            pipeline, stage_index, run_dir, params
        )

        self.provider.ensure_model(stage.model)

        source_payload = stage_json.get(map_from)
        if not isinstance(source_payload, dict) or "items" not in source_payload:
            raise RunnerError(
                f"Map stage '{stage.stage_id}' expects JSON list from '{map_from}'."
            )
        items = source_payload.get("items")
        if not isinstance(items, list):
            raise RunnerError(
                f"Map stage '{stage.stage_id}' expects JSON list from '{map_from}'."
            )

        stage_meta = {
            "stage_id": stage.stage_id,
            "model": stage.model,
            "output": stage.output,
            "mode": stage.mode,
            "map_from": map_from,
            "publish": stage.publish,
            "started_at": _utc_now(),
            "status": "started",
        }
        _write_json(stage_dir / "stage.json", stage_meta)
        _write_json(
            stage_dir / "context.json",
            {
                "map_from": map_from,
                "item_count": len(items),
                "context_all": {
                    "params": dict(params),
                    "stage_outputs": stage_outputs,
                    "stage_json": stage_json,
                },
            },
        )
        meta["stages"][stage.stage_id] = {
            "status": "started",
            "started_at": stage_meta["started_at"],
        }
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            f"stage:{stage.stage_id} status=started mode={stage.mode} map_from={map_from}",
        )

        items_root = stage_dir / "items"
        items_root.mkdir(parents=True, exist_ok=True)

        manifest_items: list[dict[str, Any]] = []
        had_failures = False

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                item = {"value": item}
            elif "value" not in item:
                if len(item) == 1:
                    item["value"] = next(iter(item.values()))
                else:
                    item["value"] = json.dumps(item, ensure_ascii=True)
            item_id = item.get("id") or _stable_item_id(item)
            item_selected = item.get("_selected", True)
            item_dir = items_root / item_id
            item_dir.mkdir(parents=True, exist_ok=True)

            item_stage_path = item_dir / "stage.json"
            if not item_selected:
                item_meta = {
                    "stage_id": stage.stage_id,
                    "item_id": item_id,
                    "item_index": index,
                    "status": "skipped",
                    "skipped_at": _utc_now(),
                }
                item_path = item_dir / "item.json"
                if not item_path.exists():
                    _write_json(item_path, item)
                if not item_stage_path.exists():
                    _write_json(item_stage_path, item_meta)
                manifest_items.append(
                    {
                        "id": item_id,
                        "_selected": False,
                        "status": "skipped",
                        "item": item,
                    }
                )
                continue

            item_output_path = _item_output_path(stage, item_dir)
            if item_output_path.exists():
                manifest_entry = {
                    "id": item_id,
                    "_selected": True,
                    "status": "completed",
                    "item": item,
                    "output_path": _relative_path(item_output_path, run_dir),
                }
                raw_path = item_dir / "raw.txt"
                if raw_path.exists():
                    manifest_entry["raw_path"] = _relative_path(raw_path, run_dir)
                manifest_items.append(manifest_entry)
                continue

            item_context = dict(context)
            item_context["item"] = item
            item_context["item_index"] = index
            item_context["item_id"] = item_id

            template_fields = _extract_template_fields(stage.prompt)
            used_context = _build_used_context(
                template_fields=template_fields,
                params=params,
                stage_outputs=stage_outputs,
                stage_json=stage_json,
                item=item,
                item_index=index,
                item_id=item_id,
            )
            rendered_prompt = _render_prompt(stage.prompt, item_context)
            item_meta = {
                "stage_id": stage.stage_id,
                "model": stage.model,
                "output": stage.output,
                "item_id": item_id,
                "item_index": index,
                "prompt": rendered_prompt,
                "started_at": _utc_now(),
                "status": "started",
            }
            _write_json(item_dir / "item.json", item)
            _write_json(item_stage_path, item_meta)
            _write_json(
                item_dir / "context.json",
                {
                    "rendered_prompt": rendered_prompt,
                    "context_all": {
                        "params": dict(params),
                        "stage_outputs": stage_outputs,
                        "stage_json": stage_json,
                        "item": item,
                        "item_index": index,
                        "item_id": item_id,
                    },
                    "context_used": used_context,
                },
            )

            try:
                response_text = self.provider.generate(
                    model=stage.model, prompt=rendered_prompt
                )
                (item_dir / "raw.txt").write_text(response_text)

                if stage.output == "json":
                    try:
                        parsed = json.loads(response_text)
                    except json.JSONDecodeError as exc:
                        raise RunnerError("Item output was not valid JSON.") from exc
                    _write_json(item_dir / "output.json", parsed)
                    output_path = item_dir / "output.json"
                else:
                    (item_dir / "output.md").write_text(response_text)
                    output_path = item_dir / "output.md"

                item_meta["completed_at"] = _utc_now()
                item_meta["status"] = "completed"
                _write_json(item_stage_path, item_meta)
                manifest_items.append(
                    {
                        "id": item_id,
                        "_selected": True,
                        "status": "completed",
                        "item": item,
                        "output_path": _relative_path(output_path, run_dir),
                        "raw_path": _relative_path(item_dir / "raw.txt", run_dir),
                    }
                )
            except Exception as exc:
                had_failures = True
                error = {
                    "stage_id": stage.stage_id,
                    "item_id": item_id,
                    "item_index": index,
                    "error": str(exc),
                }
                _write_json(item_dir / "error.json", error)
                item_meta["status"] = "failed"
                item_meta["failed_at"] = _utc_now()
                _write_json(item_stage_path, item_meta)
                manifest_items.append(
                    {
                        "id": item_id,
                        "_selected": True,
                        "status": "failed",
                        "item": item,
                        "error": str(exc),
                        "error_path": _relative_path(item_dir / "error.json", run_dir),
                    }
                )
                _append_log(
                    run_dir,
                    f"stage:{stage.stage_id} item:{item_id} status=failed error={exc}",
                )

        stage_meta["completed_at"] = _utc_now()
        stage_meta["status"] = "completed_with_errors" if had_failures else "completed"
        stage_meta["items_total"] = len(items)
        stage_meta["items_failed"] = sum(1 for entry in manifest_items if entry["status"] == "failed")
        stage_meta["items_skipped"] = sum(1 for entry in manifest_items if entry["status"] == "skipped")
        stage_meta["items_completed"] = sum(
            1 for entry in manifest_items if entry["status"] == "completed"
        )
        _write_json(stage_dir / "stage.json", stage_meta)
        _write_json(stage_dir / "output.json", {"items": manifest_items, "map_from": map_from})

        meta["stages"][stage.stage_id] = {
            "status": stage_meta["status"],
            "completed_at": stage_meta["completed_at"],
            "items_completed": stage_meta["items_completed"],
            "items_failed": stage_meta["items_failed"],
            "items_skipped": stage_meta["items_skipped"],
        }
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            (
                "stage:"
                f"{stage.stage_id} status={stage_meta['status']} "
                f"items_completed={stage_meta['items_completed']} "
                f"items_failed={stage_meta['items_failed']} "
                f"items_skipped={stage_meta['items_skipped']}"
            ),
        )

    def _publish_outputs(self, pipeline: Pipeline, run_dir: Path, meta: dict[str, Any]) -> None:
        output_dir = run_dir / "output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        published: list[dict[str, Any]] = []
        for stage in _stage_publish_enabled(pipeline):
            stage_dir = run_dir / "stages" / stage.stage_id
            if stage.mode == "map":
                items_root = stage_dir / "items"
                if not items_root.exists():
                    continue
                for item_dir in items_root.iterdir():
                    if not item_dir.is_dir():
                        continue
                    item_output = _item_output_path(stage, item_dir)
                    if not item_output.exists():
                        continue
                    dest = output_dir / stage.stage_id / item_dir.name / item_output.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item_output, dest)
                    published.append(
                        {
                            "stage_id": stage.stage_id,
                            "item_id": item_dir.name,
                            "output_path": _relative_path(dest, run_dir),
                        }
                    )
            else:
                stage_output = _stage_output_path(stage, stage_dir)
                if not stage_output.exists():
                    continue
                dest = output_dir / stage.stage_id / stage_output.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage_output, dest)
                published.append(
                    {
                        "stage_id": stage.stage_id,
                        "output_path": _relative_path(dest, run_dir),
                    }
                )

        meta["output"] = {
            "published_at": _utc_now(),
            "path": "output",
            "artifacts": published,
        }
        _write_json(run_dir / "run.json", meta)

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
        if run_dir is None and start_idx > 0:
            raise RunnerError("Starting from a later stage requires --run-dir to resume.")

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
            _append_log(run_dir, f"run status=started pipeline={pipeline.name}")
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
            _append_log(run_dir, f"run status=resumed pipeline={pipeline.name}")

        for stage in pipeline.stages[:start_idx]:
            stage_dir = run_dir / "stages" / stage.stage_id
            if not _stage_completed(stage, stage_dir):
                raise RunnerError(
                    f"Cannot start at '{stage_ids[start_idx]}': "
                    f"upstream stage '{stage.stage_id}' is incomplete."
                )

        try:
            for idx, stage in enumerate(pipeline.stages):
                if idx < start_idx or idx > stop_idx:
                    continue

                if stage.mode == "map":
                    self._run_map_stage(
                        pipeline=pipeline,
                        stage=stage,
                        stage_index=idx,
                        run_dir=run_dir,
                        params=params,
                        meta=meta,
                    )
                else:
                    self._run_single_stage(
                        pipeline=pipeline,
                        stage=stage,
                        stage_index=idx,
                        run_dir=run_dir,
                        params=params,
                        meta=meta,
                    )

                if idx == stop_idx:
                    if stop_idx == len(pipeline.stages) - 1:
                        meta["completed_at"] = _utc_now()
                        meta["status"] = "completed"
                    else:
                        meta["stopped_at"] = _utc_now()
                        meta["status"] = "stopped"
                    _write_json(run_dir / "run.json", meta)
                    _append_log(run_dir, f"run status={meta['status']}")
                    self._publish_outputs(pipeline, run_dir, meta)
                    return run_dir

            meta["completed_at"] = _utc_now()
            if any(
                stage_meta.get("status") == "completed_with_errors"
                for stage_meta in meta.get("stages", {}).values()
            ):
                meta["status"] = "completed_with_errors"
            else:
                meta["status"] = "completed"
            _write_json(run_dir / "run.json", meta)
            _append_log(run_dir, f"run status={meta['status']}")
            self._publish_outputs(pipeline, run_dir, meta)
        except Exception as exc:
            meta["status"] = "failed"
            meta["error"] = str(exc)
            meta["failed_at"] = _utc_now()
            _write_json(run_dir / "run.json", meta)
            _append_log(run_dir, f"run status=failed error={exc}")
            raise

        return run_dir
