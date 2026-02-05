from __future__ import annotations

import hashlib
import json
import re
import shutil
import string
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from promptchain.pipeline import InputFile, Pipeline, Stage
from promptchain.providers.ollama import OllamaProvider
from promptchain.providers.openai import OpenAIProvider


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
    with _LOG_LOCK:
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(f"[{timestamp}] {message}\n")


_LOG_LOCK = threading.Lock()


def _write_stage_meta(run_dir: Path, stage_id: str, payload: dict[str, Any]) -> None:
    _write_json(run_dir / f"{stage_id}.meta.json", payload)


def _logs_dir(run_dir: Path) -> Path:
    path = run_dir / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _support_dir(run_dir: Path) -> Path:
    path = run_dir / "support"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_logs_dir(run_dir: Path, stage_id: str) -> Path:
    path = _logs_dir(run_dir) / "stages" / stage_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_support_dir(run_dir: Path, stage_id: str) -> Path:
    path = _support_dir(run_dir) / "stages" / stage_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item_logs_dir(run_dir: Path, stage_id: str, item_id: str) -> Path:
    path = _stage_logs_dir(run_dir, stage_id) / "items" / item_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item_support_dir(run_dir: Path, stage_id: str, item_id: str) -> Path:
    path = _stage_support_dir(run_dir, stage_id) / "items" / item_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RunnerError(f"{label} contained invalid JSON: {path}") from exc


def _resolve_file_path(path: str, pipeline_path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (Path(pipeline_path).parent / candidate).resolve()


def _load_input_files(
    *,
    pipeline_path: str | Path,
    input_files: Mapping[str, InputFile],
) -> tuple[dict[str, str], dict[str, Any], dict[str, dict[str, Any]]]:
    inputs_text: dict[str, str] = {}
    inputs_json: dict[str, Any] = {}
    inputs_meta: dict[str, dict[str, Any]] = {}

    for name, input_file in input_files.items():
        resolved_path = _resolve_file_path(input_file.path, pipeline_path)
        if not resolved_path.exists():
            raise RunnerError(f"Input file not found: {resolved_path}")
        inputs_meta[name] = {
            "path": str(resolved_path),
            "kind": input_file.kind,
        }
        if input_file.kind == "json":
            parsed = _read_json(resolved_path, f"Input file '{name}'")
            inputs_json[name] = parsed
            inputs_text[name] = json.dumps(parsed, indent=2, ensure_ascii=True)
        else:
            inputs_text[name] = resolved_path.read_text()

    return inputs_text, inputs_json, inputs_meta


def _load_map_items_from_file(
    *,
    path: str,
    pipeline_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolved_path = _resolve_file_path(path, pipeline_path)
    if not resolved_path.exists():
        raise RunnerError(f"Map source file not found: {resolved_path}")

    kind = "json" if resolved_path.suffix.lower() == ".json" else "text"
    if kind == "json":
        payload = _read_json(resolved_path, "Map source file")
        normalized = _normalize_json_output(payload)
        items = normalized["items"]
    else:
        raw_text = resolved_path.read_text()
        lines = [line.strip() for line in raw_text.splitlines()]
        line_items = [{"value": line} for line in lines if line]
        normalized = _normalize_json_output(line_items)
        items = normalized["items"]

    meta = {
        "path": str(resolved_path),
        "kind": kind,
    }
    return items, meta


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


def _parse_json_response(response_text: str) -> Any:
    candidates: list[str] = []
    stripped = response_text.strip()
    if stripped:
        candidates.append(stripped)

    fence_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```", response_text, flags=re.IGNORECASE | re.DOTALL
    )
    if fence_match:
        fence_content = fence_match.group(1).strip()
        if fence_content:
            candidates.insert(0, fence_content)

    decoder = json.JSONDecoder()

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    for source in (stripped, response_text):
        brace = source.find("{")
        bracket = source.find("[")
        starts = [idx for idx in (brace, bracket) if idx != -1]
        if not starts:
            continue
        start = min(starts)
        try:
            parsed, _ = decoder.raw_decode(source[start:])
            return parsed
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No valid JSON found in response.", response_text, 0)


def _stage_output_paths(stage: Stage, stage_dir: Path) -> Path:
    if stage.mode == "map":
        return stage_dir / "output.json"
    return stage_dir / ("output.json" if stage.output == "json" else "output.md")


def _load_stage_output(stage: Stage, stage_dir: Path) -> tuple[str, Any | None]:
    output_path = _stage_output_paths(stage, stage_dir)
    if not output_path.exists():
        raise RunnerError(f"Missing output for stage '{stage.stage_id}' at {output_path}")
    if stage.mode == "map" or stage.output == "json":
        parsed = _read_json(output_path, f"Stage '{stage.stage_id}' output")
        rendered = json.dumps(parsed, indent=2, ensure_ascii=True)
        return rendered, parsed
    return output_path.read_text(), None


def _stage_output_path(stage: Stage, stage_dir: Path) -> Path:
    return _stage_output_paths(stage, stage_dir)


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


def _stage_dependencies(stage: Stage) -> set[str]:
    deps: set[str] = set()
    if stage.mode == "map" and stage.map_from:
        deps.add(stage.map_from)
    for field in _extract_template_fields(stage.prompt):
        if field.startswith("stage_outputs[") and field.endswith("]"):
            deps.add(field[len("stage_outputs[") : -1])
        elif field.startswith("stage_json[") and field.endswith("]"):
            deps.add(field[len("stage_json[") : -1])
    return deps


def _build_used_context(
    template_fields: list[str],
    params: Mapping[str, Any],
    stage_outputs: Mapping[str, str],
    stage_json: Mapping[str, Any],
    inputs_text: Mapping[str, str] | None = None,
    inputs_json: Mapping[str, Any] | None = None,
    item: Mapping[str, Any] | None = None,
    item_index: int | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    params_used: dict[str, Any] = {}
    stage_outputs_used: dict[str, str] = {}
    stage_json_used: dict[str, Any] = {}
    inputs_text_used: dict[str, str] = {}
    inputs_json_used: dict[str, Any] = {}
    item_used: Mapping[str, Any] | None = None
    item_index_used: int | None = None
    item_id_used: str | None = None
    item_value_used: Any | None = None
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
        if field.startswith("inputs[") and field.endswith("]"):
            key = field[len("inputs[") : -1]
            if inputs_text and key in inputs_text:
                inputs_text_used[key] = inputs_text[key]
            continue
        if field.startswith("inputs_json[") and field.endswith("]"):
            key = field[len("inputs_json[") : -1]
            if inputs_json and key in inputs_json:
                inputs_json_used[key] = inputs_json[key]
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
        if field == "item_value" and item is not None:
            item_value_used = item.get("value")
            continue
        if field in params:
            params_used[field] = params[field]
            continue
        if inputs_text and field in inputs_text:
            inputs_text_used[field] = inputs_text[field]
            continue
        if inputs_json and field in inputs_json:
            inputs_json_used[field] = inputs_json[field]
            continue

    context_used: dict[str, Any] = {
        "params": params_used,
        "stage_outputs": stage_outputs_used,
        "stage_json": stage_json_used,
        "template_fields": raw_fields,
    }
    if inputs_text_used:
        context_used["inputs"] = inputs_text_used
    if inputs_json_used:
        context_used["inputs_json"] = inputs_json_used
    if item_used is not None:
        context_used["item"] = item_used
    if item_index_used is not None:
        context_used["item_index"] = item_index_used
    if item_id_used is not None:
        context_used["item_id"] = item_id_used
    if item_value_used is not None:
        context_used["item_value"] = item_value_used
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
    publish_stages = [stage for stage in pipeline.stages if stage.publish and stage.enabled]
    if publish_stages:
        return publish_stages
    for stage in reversed(pipeline.stages):
        if stage.enabled:
            return [stage]
    return []


class Runner:
    def __init__(self, runs_root: Path | str = "runs") -> None:
        self.runs_root = Path(runs_root)
        self._providers: dict[str, Any] = {}

    def _get_provider(self, name: str):
        provider = self._providers.get(name)
        if provider is not None:
            return provider
        if name == "ollama":
            provider = OllamaProvider()
        elif name == "openai":
            provider = OpenAIProvider()
        else:
            raise RunnerError(f"Unknown provider: {name}")
        self._providers[name] = provider
        return provider

    def _gather_stage_context(
        self,
        pipeline: Pipeline,
        stage_index: int,
        run_dir: Path,
        params: Mapping[str, Any],
        stage: Stage,
    ) -> tuple[
        dict[str, Any],
        dict[str, str],
        dict[str, Any],
        dict[str, str],
        dict[str, Any],
        dict[str, dict[str, Any]],
    ]:
        stage_outputs: dict[str, str] = {}
        stage_json: dict[str, Any] = {}
        for prior in pipeline.stages[:stage_index]:
            if not prior.enabled:
                continue
            prior_dir = run_dir / "stages" / prior.stage_id
            output_text, output_json = _load_stage_output(prior, prior_dir)
            stage_outputs[prior.stage_id] = output_text
            if output_json is not None:
                stage_json[prior.stage_id] = output_json
        inputs_text, inputs_json, inputs_meta = _load_input_files(
            pipeline_path=pipeline.path,
            input_files=stage.input_files,
        )
        context = dict(params)
        context.update(inputs_text)
        context["stage_outputs"] = stage_outputs
        context["stage_json"] = stage_json
        context["inputs"] = inputs_text
        context["inputs_json"] = inputs_json
        return context, stage_outputs, stage_json, inputs_text, inputs_json, inputs_meta

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

        (
            context,
            stage_outputs,
            stage_json,
            inputs_text,
            inputs_json,
            inputs_meta,
        ) = self._gather_stage_context(pipeline, stage_index, run_dir, params, stage)

        provider = self._get_provider(stage.provider)
        provider.ensure_model(stage.model)

        template_fields = _extract_template_fields(stage.prompt)
        used_context = _build_used_context(
            template_fields=template_fields,
            params=params,
            stage_outputs=stage_outputs,
            stage_json=stage_json,
            inputs_text=inputs_text,
            inputs_json=inputs_json,
        )
        rendered_prompt = _render_prompt(stage.prompt, context)
        stage_meta = {
            "stage_id": stage.stage_id,
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
            "output": stage.output,
            "mode": stage.mode,
            "publish": stage.publish,
            "prompt": rendered_prompt,
            "started_at": _utc_now(),
            "status": "started",
        }
        _write_json(stage_dir / "stage.json", stage_meta)
        support_dir = _stage_support_dir(run_dir, stage.stage_id)
        _write_json(
            support_dir / "context.json",
            {
                "rendered_prompt": rendered_prompt,
                "context_all": {
                    "params": dict(params),
                    "inputs": inputs_text,
                    "inputs_json": inputs_json,
                    "inputs_meta": inputs_meta,
                    "stage_outputs": stage_outputs,
                    "stage_json": stage_json,
                },
                "context_used": used_context,
            },
        )
        _write_json(
            support_dir / "request.json",
            {
                "provider": stage.provider,
                "model": stage.model,
                "temperature": stage.temperature,
                "reasoning_effort": stage.reasoning_effort,
                "prompt": rendered_prompt,
            },
        )
        meta["stages"][stage.stage_id] = {
            "status": "started",
            "started_at": stage_meta["started_at"],
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
        }
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            (
                f"stage:{stage.stage_id} status=started mode={stage.mode} "
                f"provider={stage.provider} model={stage.model} "
                f"temperature={stage.temperature} reasoning_effort={stage.reasoning_effort}"
            ),
        )

        try:
            response_text = provider.generate(
                model=stage.model,
                prompt=rendered_prompt,
                temperature=stage.temperature,
                reasoning_effort=stage.reasoning_effort,
            )
        except RuntimeError as exc:
            if stage.reasoning_effort and "reasoning.effort" in str(exc):
                raise RunnerError(
                    f"Stage '{stage.stage_id}' rejected reasoning_effort "
                    f"'{stage.reasoning_effort}'. Remove reasoning_effort or "
                    "use a reasoning-capable model."
                ) from exc
            raise

        logs_dir = _stage_logs_dir(run_dir, stage.stage_id)
        raw_path = logs_dir / "raw.txt"
        raw_path.write_text(response_text)
        _write_json(
            support_dir / "response.json",
            {
                "provider": stage.provider,
                "model": stage.model,
                "response_chars": len(response_text),
                "raw_path": _relative_path(raw_path, run_dir),
            },
        )

        if stage.output == "json":
            try:
                parsed = _parse_json_response(response_text)
                normalized = _normalize_json_output(parsed)
            except (json.JSONDecodeError, RunnerError) as exc:
                error_message = "Stage output was not valid JSON list."
                error = {
                    "stage_id": stage.stage_id,
                    "error": "Invalid JSON output format.",
                    "detail": str(exc),
                }
                error_path = logs_dir / "error.json"
                _write_json(error_path, error)
                stage_meta["status"] = "failed"
                stage_meta["failed_at"] = _utc_now()
                _write_json(stage_dir / "stage.json", stage_meta)
                _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                meta["stages"][stage.stage_id] = {
                    "status": "failed",
                    "failed_at": stage_meta["failed_at"],
                    "error": error_message,
                    "error_path": _relative_path(error_path, run_dir),
                    "temperature": stage.temperature,
                    "reasoning_effort": stage.reasoning_effort,
                    "enabled": stage.enabled,
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
        _write_stage_meta(run_dir, stage.stage_id, stage_meta)
        meta["stages"][stage.stage_id] = {
            "status": "completed",
            "completed_at": stage_meta["completed_at"],
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
        }
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            (
                f"stage:{stage.stage_id} status=completed "
                f"provider={stage.provider} model={stage.model} "
                f"temperature={stage.temperature} reasoning_effort={stage.reasoning_effort}"
            ),
        )

    def _run_map_stage(
        self,
        *,
        pipeline: Pipeline,
        stage: Stage,
        stage_index: int,
        run_dir: Path,
        params: Mapping[str, Any],
        meta: dict[str, Any],
        concurrency_override: int | None,
    ) -> bool:
        stage_dir = run_dir / "stages" / stage.stage_id
        stage_dir.mkdir(parents=True, exist_ok=True)

        if _stage_completed(stage, stage_dir):
            return

        if not stage.map_from and not stage.map_from_file:
            raise RunnerError(
                f"Map stage '{stage.stage_id}' is missing map_from or map_from_file."
            )

        map_from = stage.map_from
        map_from_file = stage.map_from_file
        map_source_meta: dict[str, Any] | None = None

        if map_from:
            if map_from not in [s.stage_id for s in pipeline.stages]:
                raise RunnerError(
                    f"Map stage '{stage.stage_id}' references unknown stage '{map_from}'."
                )

            if map_from not in [s.stage_id for s in pipeline.stages[:stage_index]]:
                raise RunnerError(
                    f"Map stage '{stage.stage_id}' must reference an upstream stage."
                )

        (
            context,
            stage_outputs,
            stage_json,
            inputs_text,
            inputs_json,
            inputs_meta,
        ) = self._gather_stage_context(pipeline, stage_index, run_dir, params, stage)

        provider = self._get_provider(stage.provider)
        provider.ensure_model(stage.model)

        if stage.batch_enabled and stage.provider != "openai":
            raise RunnerError(
                f"Batch mode for stage '{stage.stage_id}' is only supported with OpenAI."
            )
        if stage.batch_enabled and (concurrency_override is not None or stage.concurrency_enabled):
            raise RunnerError(
                f"Stage '{stage.stage_id}' cannot enable both batch and concurrency."
            )

        if map_from_file:
            items, map_source_meta = _load_map_items_from_file(
                path=map_from_file,
                pipeline_path=pipeline.path,
            )
        else:
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

        execution_mode = "serial"
        max_in_flight: int | None = 1
        if stage.batch_enabled:
            execution_mode = "batch"
            max_in_flight = None
        elif stage.provider == "openai":
            if concurrency_override is not None:
                if concurrency_override < 1:
                    raise RunnerError("Concurrency override must be >= 1.")
                max_in_flight = concurrency_override
            elif stage.concurrency_enabled:
                max_in_flight = stage.concurrency_max_in_flight or 4
            if max_in_flight and max_in_flight > 1:
                execution_mode = "concurrent"

        stage_meta = {
            "stage_id": stage.stage_id,
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
            "execution_mode": execution_mode,
            "max_in_flight": max_in_flight,
            "output": stage.output,
            "mode": stage.mode,
            "map_from": map_from,
            "map_from_file": map_from_file,
            "publish": stage.publish,
            "started_at": _utc_now(),
            "status": "started",
        }
        _write_json(stage_dir / "stage.json", stage_meta)
        support_dir = _stage_support_dir(run_dir, stage.stage_id)
        _write_json(
            support_dir / "context.json",
            {
                "map_from": map_from,
                "map_from_file": map_from_file,
                "map_from_meta": map_source_meta,
                "item_count": len(items),
                "context_all": {
                    "params": dict(params),
                    "inputs": inputs_text,
                    "inputs_json": inputs_json,
                    "inputs_meta": inputs_meta,
                    "stage_outputs": stage_outputs,
                    "stage_json": stage_json,
                },
            },
        )
        meta["stages"][stage.stage_id] = {
            "status": "started",
            "started_at": stage_meta["started_at"],
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
            "execution_mode": execution_mode,
            "max_in_flight": max_in_flight,
        }
        if execution_mode == "concurrent":
            meta.setdefault("concurrency", {"used": False, "stages": {}})
            meta["concurrency"]["stages"][stage.stage_id] = {
                "mode": execution_mode,
                "max_in_flight": max_in_flight,
            }
            meta["concurrency"]["used"] = True
        if execution_mode == "batch":
            meta.setdefault("batch", {"used": False, "stages": {}})
            meta["batch"]["stages"][stage.stage_id] = {
                "mode": execution_mode,
                "status": "submitted",
            }
            meta["batch"]["used"] = True
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            (
                f"stage:{stage.stage_id} status=started mode={stage.mode} map_from={map_from} "
                f"provider={stage.provider} model={stage.model} "
                f"temperature={stage.temperature} reasoning_effort={stage.reasoning_effort}"
            ),
        )
        if execution_mode == "concurrent":
            _append_log(
                run_dir,
                f"Stage {stage.stage_id} running in CONCURRENT mode (max_in_flight={max_in_flight})",
            )
        elif execution_mode == "batch":
            _append_log(
                run_dir,
                f"Stage {stage.stage_id} running in BATCH mode (submit/collect)",
            )
        else:
            _append_log(
                run_dir,
                f"Stage {stage.stage_id} running in SERIAL mode",
            )

        items_root = stage_dir / "items"
        items_root.mkdir(parents=True, exist_ok=True)

        manifest_items: list[dict[str, Any] | None] = [None] * len(items)
        had_failures = False

        work_items: list[dict[str, Any]] = []

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
                manifest_items[index] = {
                    "id": item_id,
                    "_selected": False,
                    "status": "skipped",
                    "item": item,
                }
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
                raw_path = _item_logs_dir(run_dir, stage.stage_id, item_id) / "raw.txt"
                if raw_path.exists():
                    manifest_entry["raw_path"] = _relative_path(raw_path, run_dir)
                manifest_items[index] = manifest_entry
                continue

            item_context = dict(context)
            item_context["item"] = item
            item_context["item_value"] = item.get("value")
            item_context["item_index"] = index
            item_context["item_id"] = item_id

            template_fields = _extract_template_fields(stage.prompt)
            used_context = _build_used_context(
                template_fields=template_fields,
                params=params,
                stage_outputs=stage_outputs,
                stage_json=stage_json,
                inputs_text=inputs_text,
                inputs_json=inputs_json,
                item=item,
                item_index=index,
                item_id=item_id,
            )
            rendered_prompt = _render_prompt(stage.prompt, item_context)

            work_items.append(
                {
                    "index": index,
                    "item": item,
                    "item_id": item_id,
                    "item_dir": item_dir,
                    "item_stage_path": item_stage_path,
                    "rendered_prompt": rendered_prompt,
                    "used_context": used_context,
                }
            )

        if execution_mode == "batch":
            batch_support_dir = _stage_support_dir(run_dir, stage.stage_id)
            batch_state_path = batch_support_dir / "batch.json"

            if batch_state_path.exists():
                batch_state = _read_json(batch_state_path, "Batch state")
                batch_id = batch_state.get("batch_id")
                if not isinstance(batch_id, str):
                    raise RunnerError(f"Batch state missing batch_id for stage '{stage.stage_id}'.")
                batch_info = provider.retrieve_batch(batch_id)
                batch_status = batch_info.get("status")
                output_file_id = batch_info.get("output_file_id")
                error_file_id = batch_info.get("error_file_id")
                batch_state["status"] = batch_status
                batch_state["output_file_id"] = output_file_id
                batch_state["error_file_id"] = error_file_id
                _write_json(batch_state_path, batch_state)

                if batch_status in {"failed", "expired", "canceled"}:
                    stage_meta["status"] = "failed"
                    stage_meta["batch_id"] = batch_id
                    stage_meta["batch_status"] = batch_status
                    stage_meta["failed_at"] = _utc_now()
                    _write_json(stage_dir / "stage.json", stage_meta)
                    _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                    meta["stages"][stage.stage_id] = {
                        "status": "failed",
                        "batch_status": batch_status,
                        "batch_id": batch_id,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                        "execution_mode": execution_mode,
                    }
                    meta.setdefault("batch", {"used": False, "stages": {}})
                    meta["batch"]["stages"][stage.stage_id] = {
                        "mode": execution_mode,
                        "status": batch_status,
                    }
                    _write_json(run_dir / "run.json", meta)
                    _append_log(
                        run_dir,
                        f"stage:{stage.stage_id} status=failed batch_id={batch_id} batch_status={batch_status}",
                    )
                    raise RunnerError(
                        f"Batch for stage '{stage.stage_id}' failed with status '{batch_status}'."
                    )

                if batch_status != "completed" or not output_file_id:
                    stage_meta["status"] = "batch_pending"
                    stage_meta["batch_id"] = batch_id
                    stage_meta["batch_status"] = batch_status
                    stage_meta["updated_at"] = _utc_now()
                    _write_json(stage_dir / "stage.json", stage_meta)
                    _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                    meta["stages"][stage.stage_id] = {
                        "status": "batch_pending",
                        "batch_status": batch_status,
                        "batch_id": batch_id,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                        "execution_mode": execution_mode,
                    }
                    meta.setdefault("batch", {"used": False, "stages": {}})
                    meta["batch"]["stages"][stage.stage_id] = {
                        "mode": execution_mode,
                        "status": "pending",
                    }
                    _write_json(run_dir / "run.json", meta)
                    _append_log(
                        run_dir,
                        f"stage:{stage.stage_id} status=batch_pending batch_id={batch_id} batch_status={batch_status}",
                    )
                    return True

                output_lines = provider.download_file(output_file_id).splitlines()
                error_lines: list[str] = []
                if error_file_id:
                    error_lines = provider.download_file(error_file_id).splitlines()

                request_map = {
                    entry["custom_id"]: entry
                    for entry in batch_state.get("requests", [])
                    if isinstance(entry, dict) and isinstance(entry.get("custom_id"), str)
                }

                def handle_line(line: str, is_error: bool = False) -> None:
                    nonlocal had_failures
                    if not line.strip():
                        return
                    payload = json.loads(line)
                    custom_id = payload.get("custom_id")
                    request_entry = request_map.get(custom_id)
                    if not request_entry:
                        return
                    index = request_entry["item_index"]
                    item = request_entry["item"]
                    item_id = request_entry["item_id"]
                    item_dir = items_root / item_id
                    item_stage_path = item_dir / "stage.json"

                    if is_error or payload.get("error"):
                        error = payload.get("error") or payload
                        error_path = _item_logs_dir(run_dir, stage.stage_id, item_id) / "error.json"
                        _write_json(error_path, {"error": error, "custom_id": custom_id})
                        item_meta = _read_json(item_stage_path, "Item stage meta")
                        item_meta["status"] = "failed"
                        item_meta["failed_at"] = _utc_now()
                        _write_json(item_stage_path, item_meta)
                        manifest_items[index] = {
                            "id": item_id,
                            "_selected": True,
                            "status": "failed",
                            "item": item,
                            "error": str(error),
                            "error_path": _relative_path(error_path, run_dir),
                        }
                        had_failures = True
                        _append_log(
                            run_dir,
                            f"stage:{stage.stage_id} item:{item_id} status=failed error=batch_error",
                        )
                        return

                    response = payload.get("response", {})
                    status_code = response.get("status_code")
                    body = response.get("body")
                    if status_code != 200 or not isinstance(body, dict):
                        error_path = _item_logs_dir(run_dir, stage.stage_id, item_id) / "error.json"
                        _write_json(
                            error_path,
                            {
                                "error": "batch_response_error",
                                "status_code": status_code,
                                "custom_id": custom_id,
                            },
                        )
                        item_meta = _read_json(item_stage_path, "Item stage meta")
                        item_meta["status"] = "failed"
                        item_meta["failed_at"] = _utc_now()
                        _write_json(item_stage_path, item_meta)
                        manifest_items[index] = {
                            "id": item_id,
                            "_selected": True,
                            "status": "failed",
                            "item": item,
                            "error": f"batch_response_error status_code={status_code}",
                            "error_path": _relative_path(error_path, run_dir),
                        }
                        had_failures = True
                        return

                    response_text = provider.extract_text(body)
                    item_logs_dir = _item_logs_dir(run_dir, stage.stage_id, item_id)
                    raw_path = item_logs_dir / "raw.txt"
                    raw_path.write_text(response_text)

                    if stage.output == "json":
                        try:
                            parsed = _parse_json_response(response_text)
                        except json.JSONDecodeError as exc:
                            error_path = item_logs_dir / "error.json"
                            _write_json(error_path, {"error": str(exc)})
                            item_meta = _read_json(item_stage_path, "Item stage meta")
                            item_meta["status"] = "failed"
                            item_meta["failed_at"] = _utc_now()
                            _write_json(item_stage_path, item_meta)
                            manifest_items[index] = {
                                "id": item_id,
                                "_selected": True,
                                "status": "failed",
                                "item": item,
                                "error": str(exc),
                                "error_path": _relative_path(error_path, run_dir),
                            }
                            had_failures = True
                            return
                        _write_json(item_dir / "output.json", parsed)
                        output_path = item_dir / "output.json"
                    else:
                        (item_dir / "output.md").write_text(response_text)
                        output_path = item_dir / "output.md"

                    item_meta = _read_json(item_stage_path, "Item stage meta")
                    item_meta["status"] = "completed"
                    item_meta["completed_at"] = _utc_now()
                    _write_json(item_stage_path, item_meta)
                    manifest_items[index] = {
                        "id": item_id,
                        "_selected": True,
                        "status": "completed",
                        "item": item,
                        "output_path": _relative_path(output_path, run_dir),
                        "raw_path": _relative_path(raw_path, run_dir),
                    }
                    _append_log(
                        run_dir,
                        f"stage:{stage.stage_id} item:{item_id} status=completed",
                    )

                for line in output_lines:
                    handle_line(line, is_error=False)
                for line in error_lines:
                    handle_line(line, is_error=True)

                for entry in request_map.values():
                    index = entry["item_index"]
                    if manifest_items[index] is not None:
                        continue
                    item_id = entry["item_id"]
                    item = entry["item"]
                    error_path = _item_logs_dir(run_dir, stage.stage_id, item_id) / "error.json"
                    _write_json(
                        error_path,
                        {"error": "missing_batch_result", "custom_id": entry["custom_id"]},
                    )
                    item_stage_path = (items_root / item_id) / "stage.json"
                    if item_stage_path.exists():
                        item_meta = _read_json(item_stage_path, "Item stage meta")
                        item_meta["status"] = "failed"
                        item_meta["failed_at"] = _utc_now()
                        _write_json(item_stage_path, item_meta)
                    manifest_items[index] = {
                        "id": item_id,
                        "_selected": True,
                        "status": "failed",
                        "item": item,
                        "error": "missing_batch_result",
                        "error_path": _relative_path(error_path, run_dir),
                    }
                    had_failures = True

            else:
                if not work_items:
                    manifest_items_final = [entry for entry in manifest_items if entry is not None]
                    stage_meta["completed_at"] = _utc_now()
                    stage_meta["status"] = "completed"
                    stage_meta["items_total"] = len(items)
                    stage_meta["items_failed"] = 0
                    stage_meta["items_skipped"] = sum(
                        1 for entry in manifest_items_final if entry["status"] == "skipped"
                    )
                    stage_meta["items_completed"] = sum(
                        1 for entry in manifest_items_final if entry["status"] == "completed"
                    )
                    _write_json(stage_dir / "stage.json", stage_meta)
                    _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                    _write_json(
                        stage_dir / "output.json",
                        {
                            "items": manifest_items_final,
                            "map_from": map_from,
                            "map_from_file": map_from_file,
                        },
                    )
                    meta["stages"][stage.stage_id] = {
                        "status": stage_meta["status"],
                        "completed_at": stage_meta["completed_at"],
                        "items_completed": stage_meta["items_completed"],
                        "items_failed": stage_meta["items_failed"],
                        "items_skipped": stage_meta["items_skipped"],
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                        "execution_mode": execution_mode,
                    }
                    _write_json(run_dir / "run.json", meta)
                    _append_log(
                        run_dir,
                        (
                            "stage:"
                            f"{stage.stage_id} status={stage_meta['status']} "
                            f"items_completed={stage_meta['items_completed']} "
                            f"items_failed={stage_meta['items_failed']} "
                            f"items_skipped={stage_meta['items_skipped']} "
                            f"provider={stage.provider} model={stage.model}"
                        ),
                    )
                    return False

                input_path = batch_support_dir / "batch_input.jsonl"
                request_entries: list[dict[str, Any]] = []
                with input_path.open("w", encoding="utf-8") as handle:
                    for work in work_items:
                        item = work["item"]
                        item_id = work["item_id"]
                        index = work["index"]
                        custom_id = f"{item_id}:{index}"
                        body: dict[str, Any] = {
                            "model": stage.model,
                            "input": [{"role": "user", "content": work["rendered_prompt"]}],
                        }
                        if stage.temperature is not None:
                            body["temperature"] = stage.temperature
                        if stage.reasoning_effort:
                            body["reasoning"] = {"effort": stage.reasoning_effort}
                        entry = {
                            "custom_id": custom_id,
                            "method": "POST",
                            "url": "/v1/responses",
                            "body": body,
                        }
                        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
                        request_entries.append(
                            {
                                "custom_id": custom_id,
                                "item_id": item_id,
                                "item_index": index,
                                "item": item,
                            }
                        )

                        item_meta = {
                            "stage_id": stage.stage_id,
                            "provider": stage.provider,
                            "model": stage.model,
                            "temperature": stage.temperature,
                            "reasoning_effort": stage.reasoning_effort,
                            "execution_mode": execution_mode,
                            "output": stage.output,
                            "item_id": item_id,
                            "item_index": index,
                            "prompt": work["rendered_prompt"],
                            "status": "submitted",
                            "submitted_at": _utc_now(),
                            "custom_id": custom_id,
                        }
                        _write_json(work["item_dir"] / "item.json", item)
                        _write_json(work["item_stage_path"], item_meta)
                        item_support_dir = _item_support_dir(run_dir, stage.stage_id, item_id)
                        _write_json(
                            item_support_dir / "context.json",
                            {
                                "rendered_prompt": work["rendered_prompt"],
                                "context_all": {
                                    "params": dict(params),
                                    "inputs": inputs_text,
                                    "inputs_json": inputs_json,
                                    "inputs_meta": inputs_meta,
                                    "stage_outputs": stage_outputs,
                                    "stage_json": stage_json,
                                    "item": item,
                                    "item_value": item.get("value"),
                                    "item_index": index,
                                    "item_id": item_id,
                                },
                                "context_used": work["used_context"],
                            },
                        )
                        _write_json(
                            item_support_dir / "request.json",
                            {
                                "provider": stage.provider,
                                "model": stage.model,
                                "temperature": stage.temperature,
                                "reasoning_effort": stage.reasoning_effort,
                                "prompt": work["rendered_prompt"],
                            },
                        )
                        _append_log(
                            run_dir,
                            f"stage:{stage.stage_id} item:{item_id} status=submitted",
                        )

                upload_payload = provider.upload_batch_file(str(input_path))
                input_file_id = upload_payload.get("id")
                if not isinstance(input_file_id, str):
                    raise RunnerError("OpenAI batch upload did not return a file id.")
                batch_payload = provider.create_batch(
                    input_file_id,
                    metadata={"stage_id": stage.stage_id, "run_id": meta.get("run_id", "")},
                )
                batch_id = batch_payload.get("id")
                if not isinstance(batch_id, str):
                    raise RunnerError("OpenAI batch creation did not return a batch id.")
                batch_state = {
                    "batch_id": batch_id,
                    "input_file_id": input_file_id,
                    "status": batch_payload.get("status"),
                    "submitted_at": _utc_now(),
                    "requests": request_entries,
                }
                _write_json(batch_state_path, batch_state)
                stage_meta["status"] = "batch_submitted"
                stage_meta["batch_id"] = batch_id
                stage_meta["batch_status"] = batch_state.get("status")
                _write_json(stage_dir / "stage.json", stage_meta)
                _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                meta["stages"][stage.stage_id] = {
                    "status": "batch_submitted",
                    "batch_id": batch_id,
                    "batch_status": batch_state.get("status"),
                    "provider": stage.provider,
                    "model": stage.model,
                    "temperature": stage.temperature,
                    "reasoning_effort": stage.reasoning_effort,
                    "enabled": stage.enabled,
                    "execution_mode": execution_mode,
                }
                _write_json(run_dir / "run.json", meta)
                _append_log(
                    run_dir,
                    f"stage:{stage.stage_id} status=batch_submitted batch_id={batch_id}",
                )
                _append_log(
                    run_dir,
                    f"To resume batch: re-run with --run-dir {run_dir}",
                )
                return True

            manifest_items_final = [entry for entry in manifest_items if entry is not None]
            stage_meta["completed_at"] = _utc_now()
            stage_meta["status"] = "completed_with_errors" if had_failures else "completed"
            stage_meta["items_total"] = len(items)
            stage_meta["items_failed"] = sum(
                1 for entry in manifest_items_final if entry["status"] == "failed"
            )
            stage_meta["items_skipped"] = sum(
                1 for entry in manifest_items_final if entry["status"] == "skipped"
            )
            stage_meta["items_completed"] = sum(
                1 for entry in manifest_items_final if entry["status"] == "completed"
            )
            _write_json(stage_dir / "stage.json", stage_meta)
            _write_stage_meta(run_dir, stage.stage_id, stage_meta)
            _write_json(
                stage_dir / "output.json",
                {
                    "items": manifest_items_final,
                    "map_from": map_from,
                    "map_from_file": map_from_file,
                },
            )
            meta["stages"][stage.stage_id] = {
                "status": stage_meta["status"],
                "completed_at": stage_meta["completed_at"],
                "items_completed": stage_meta["items_completed"],
                "items_failed": stage_meta["items_failed"],
                "items_skipped": stage_meta["items_skipped"],
                "provider": stage.provider,
                "model": stage.model,
                "temperature": stage.temperature,
                "reasoning_effort": stage.reasoning_effort,
                "enabled": stage.enabled,
                "execution_mode": execution_mode,
            }
            meta.setdefault("batch", {"used": False, "stages": {}})
            meta["batch"]["stages"][stage.stage_id] = {
                "mode": execution_mode,
                "status": stage_meta["status"],
            }
            _write_json(run_dir / "run.json", meta)
            _append_log(
                run_dir,
                (
                    "stage:"
                    f"{stage.stage_id} status={stage_meta['status']} "
                    f"items_completed={stage_meta['items_completed']} "
                    f"items_failed={stage_meta['items_failed']} "
                    f"items_skipped={stage_meta['items_skipped']} "
                    f"provider={stage.provider} model={stage.model}"
                ),
            )
            return False

        def process_item(work: dict[str, Any]) -> tuple[int, dict[str, Any], bool]:
            index = work["index"]
            item = work["item"]
            item_id = work["item_id"]
            item_dir = work["item_dir"]
            item_stage_path = work["item_stage_path"]
            rendered_prompt = work["rendered_prompt"]
            used_context = work["used_context"]

            item_meta = {
                "stage_id": stage.stage_id,
                "provider": stage.provider,
                "model": stage.model,
                "temperature": stage.temperature,
                "reasoning_effort": stage.reasoning_effort,
                "execution_mode": execution_mode,
                "max_in_flight": max_in_flight,
                "output": stage.output,
                "item_id": item_id,
                "item_index": index,
                "prompt": rendered_prompt,
                "started_at": _utc_now(),
                "status": "started",
            }
            _write_json(item_dir / "item.json", item)
            _write_json(item_stage_path, item_meta)
            item_support_dir = _item_support_dir(run_dir, stage.stage_id, item_id)
            _write_json(
                item_support_dir / "context.json",
                {
                    "rendered_prompt": rendered_prompt,
                    "context_all": {
                        "params": dict(params),
                        "inputs": inputs_text,
                        "inputs_json": inputs_json,
                        "inputs_meta": inputs_meta,
                        "stage_outputs": stage_outputs,
                        "stage_json": stage_json,
                        "item": item,
                        "item_value": item.get("value"),
                        "item_index": index,
                        "item_id": item_id,
                    },
                    "context_used": used_context,
                },
            )
            _write_json(
                item_support_dir / "request.json",
                {
                    "provider": stage.provider,
                    "model": stage.model,
                    "temperature": stage.temperature,
                    "reasoning_effort": stage.reasoning_effort,
                    "prompt": rendered_prompt,
                },
            )
            _append_log(
                run_dir,
                (
                    f"stage:{stage.stage_id} item:{item_id} status=started "
                    f"mode={execution_mode}"
                ),
            )

            try:
                try:
                    response_text = provider.generate(
                        model=stage.model,
                        prompt=rendered_prompt,
                        temperature=stage.temperature,
                        reasoning_effort=stage.reasoning_effort,
                    )
                except RuntimeError as exc:
                    if stage.reasoning_effort and "reasoning.effort" in str(exc):
                        raise RunnerError(
                            f"Stage '{stage.stage_id}' rejected reasoning_effort "
                            f"'{stage.reasoning_effort}'. Remove reasoning_effort or "
                            "use a reasoning-capable model."
                        ) from exc
                    raise

                item_logs_dir = _item_logs_dir(run_dir, stage.stage_id, item_id)
                raw_path = item_logs_dir / "raw.txt"
                raw_path.write_text(response_text)
                _write_json(
                    item_support_dir / "response.json",
                    {
                        "provider": stage.provider,
                        "model": stage.model,
                        "response_chars": len(response_text),
                        "raw_path": _relative_path(raw_path, run_dir),
                    },
                )

                if stage.output == "json":
                    try:
                        parsed = _parse_json_response(response_text)
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
                _append_log(
                    run_dir,
                    f"stage:{stage.stage_id} item:{item_id} status=completed",
                )
                return (
                    index,
                    {
                        "id": item_id,
                        "_selected": True,
                        "status": "completed",
                        "item": item,
                        "output_path": _relative_path(output_path, run_dir),
                        "raw_path": _relative_path(raw_path, run_dir),
                    },
                    False,
                )
            except Exception as exc:
                error = {
                    "stage_id": stage.stage_id,
                    "item_id": item_id,
                    "item_index": index,
                    "error": str(exc),
                }
                error_path = _item_logs_dir(run_dir, stage.stage_id, item_id) / "error.json"
                _write_json(error_path, error)
                item_meta["status"] = "failed"
                item_meta["failed_at"] = _utc_now()
                _write_json(item_stage_path, item_meta)
                _append_log(
                    run_dir,
                    f"stage:{stage.stage_id} item:{item_id} status=failed error={exc}",
                )
                return (
                    index,
                    {
                        "id": item_id,
                        "_selected": True,
                        "status": "failed",
                        "item": item,
                        "error": str(exc),
                        "error_path": _relative_path(error_path, run_dir),
                    },
                    True,
                )

        if execution_mode == "concurrent" and work_items:
            with ThreadPoolExecutor(max_workers=max_in_flight) as executor:
                futures = [executor.submit(process_item, work) for work in work_items]
                for future in as_completed(futures):
                    index, entry, failed = future.result()
                    manifest_items[index] = entry
                    if failed:
                        had_failures = True
        else:
            for work in work_items:
                index, entry, failed = process_item(work)
                manifest_items[index] = entry
                if failed:
                    had_failures = True

        manifest_items_final: list[dict[str, Any]] = [
            entry for entry in manifest_items if entry is not None
        ]

        stage_meta["completed_at"] = _utc_now()
        stage_meta["status"] = "completed_with_errors" if had_failures else "completed"
        stage_meta["items_total"] = len(items)
        stage_meta["items_failed"] = sum(
            1 for entry in manifest_items_final if entry["status"] == "failed"
        )
        stage_meta["items_skipped"] = sum(
            1 for entry in manifest_items_final if entry["status"] == "skipped"
        )
        stage_meta["items_completed"] = sum(
            1 for entry in manifest_items_final if entry["status"] == "completed"
        )
        _write_json(stage_dir / "stage.json", stage_meta)
        _write_stage_meta(run_dir, stage.stage_id, stage_meta)
        _write_json(
            stage_dir / "output.json",
            {
                "items": manifest_items_final,
                "map_from": map_from,
                "map_from_file": map_from_file,
            },
        )

        meta["stages"][stage.stage_id] = {
            "status": stage_meta["status"],
            "completed_at": stage_meta["completed_at"],
            "items_completed": stage_meta["items_completed"],
            "items_failed": stage_meta["items_failed"],
            "items_skipped": stage_meta["items_skipped"],
            "provider": stage.provider,
            "model": stage.model,
            "temperature": stage.temperature,
            "reasoning_effort": stage.reasoning_effort,
            "enabled": stage.enabled,
            "execution_mode": execution_mode,
            "max_in_flight": max_in_flight,
        }
        _write_json(run_dir / "run.json", meta)
        _append_log(
            run_dir,
            (
                "stage:"
                f"{stage.stage_id} status={stage_meta['status']} "
                f"items_completed={stage_meta['items_completed']} "
                f"items_failed={stage_meta['items_failed']} "
                f"items_skipped={stage_meta['items_skipped']} "
                f"provider={stage.provider} model={stage.model}"
            ),
        )
        return False

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
        concurrency_override: int | None = None,
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
                "pipeline_provider": pipeline.provider,
                "pipeline_model": pipeline.model,
                "pipeline_temperature": pipeline.temperature,
                "pipeline_reasoning_effort": pipeline.reasoning_effort,
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
            if not stage.enabled:
                continue
            stage_dir = run_dir / "stages" / stage.stage_id
            if not _stage_completed(stage, stage_dir):
                raise RunnerError(
                    f"Cannot start at '{stage_ids[start_idx]}': "
                    f"upstream stage '{stage.stage_id}' is incomplete."
                )

        disabled_stage_ids = {stage.stage_id for stage in pipeline.stages if not stage.enabled}

        try:
            for idx, stage in enumerate(pipeline.stages):
                if idx < start_idx or idx > stop_idx:
                    continue

                if not stage.enabled:
                    stage_dir = run_dir / "stages" / stage.stage_id
                    stage_dir.mkdir(parents=True, exist_ok=True)
                    skipped_at = _utc_now()
                    stage_meta = {
                        "stage_id": stage.stage_id,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                        "output": stage.output,
                        "mode": stage.mode,
                        "map_from": stage.map_from,
                        "map_from_file": stage.map_from_file,
                        "publish": stage.publish,
                        "status": "skipped",
                        "skip_reason": "disabled_in_yaml",
                        "skipped_at": skipped_at,
                    }
                    _write_json(stage_dir / "stage.json", stage_meta)
                    _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                    meta["stages"][stage.stage_id] = {
                        "status": "skipped",
                        "skip_reason": "disabled_in_yaml",
                        "skipped_at": skipped_at,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                    }
                    _write_json(run_dir / "run.json", meta)
                    _append_log(
                        run_dir,
                        f"Stage {stage.stage_id} SKIPPED (disabled in pipeline yaml)",
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
                    continue

                disabled_dep = None
                for dep in _stage_dependencies(stage):
                    if dep in disabled_stage_ids:
                        disabled_dep = dep
                        break
                if disabled_dep:
                    message = (
                        f"Cannot run stage '{stage.stage_id}': dependency '{disabled_dep}' "
                        "is disabled in pipeline yaml (enabled=false)."
                    )
                    stage_meta = {
                        "stage_id": stage.stage_id,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                        "output": stage.output,
                        "mode": stage.mode,
                        "map_from": stage.map_from,
                        "map_from_file": stage.map_from_file,
                        "publish": stage.publish,
                        "status": "failed",
                        "error": "disabled_dependency",
                        "dependency": disabled_dep,
                        "failed_at": _utc_now(),
                    }
                    _write_stage_meta(run_dir, stage.stage_id, stage_meta)
                    meta["stages"][stage.stage_id] = {
                        "status": "failed",
                        "error": "disabled_dependency",
                        "dependency": disabled_dep,
                        "provider": stage.provider,
                        "model": stage.model,
                        "temperature": stage.temperature,
                        "reasoning_effort": stage.reasoning_effort,
                        "enabled": stage.enabled,
                    }
                    _write_json(run_dir / "run.json", meta)
                    _append_log(
                        run_dir,
                        (
                            f"stage:{stage.stage_id} status=failed "
                            f"error=disabled_dependency dependency={disabled_dep}"
                        ),
                    )
                    raise RunnerError(message)

                if stage.mode == "map":
                    pending = self._run_map_stage(
                        pipeline=pipeline,
                        stage=stage,
                        stage_index=idx,
                        run_dir=run_dir,
                        params=params,
                        meta=meta,
                        concurrency_override=concurrency_override,
                    )
                    if pending:
                        meta["status"] = "batch_pending"
                        meta["batch_pending_at"] = _utc_now()
                        _write_json(run_dir / "run.json", meta)
                        _append_log(run_dir, "run status=batch_pending")
                        return run_dir
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
