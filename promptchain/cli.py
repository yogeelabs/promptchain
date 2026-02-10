from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from promptchain.pipeline import PipelineError, load_pipeline
from promptchain.runner import Runner, RunnerError


def _parse_params(unknown: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    idx = 0
    while idx < len(unknown):
        token = unknown[idx]
        if not token.startswith("--"):
            raise RunnerError(f"Unexpected argument: {token}")
        key = token[2:]
        if "=" in key:
            name, value = key.split("=", 1)
            if not name:
                raise RunnerError("Parameter name cannot be empty.")
            params[name] = value
            idx += 1
            continue
        if idx + 1 >= len(unknown):
            raise RunnerError(f"Missing value for parameter: {key}")
        value = unknown[idx + 1]
        params[key] = value
        idx += 2
    return params


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="promptchain")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a pipeline")
    run_parser.add_argument("--pipeline", required=True, help="Path to pipeline YAML")
    run_parser.add_argument("--run-dir", help="Resume an existing run directory")
    run_parser.add_argument("--from-stage", help="Start execution from a stage id")
    run_parser.add_argument("--stop-after", help="Stop execution after a stage id")
    run_parser.add_argument("--stage", help="Run only a single stage id")
    run_parser.add_argument(
        "--concurrency",
        type=int,
        help="Override max in-flight requests for map stages (OpenAI only).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args, unknown = parser.parse_known_args(argv)

    if args.command == "run":
        try:
            params = _parse_params(unknown)
            if args.run_dir and params:
                raise RunnerError("Do not pass parameters when resuming a run.")
            pipeline = load_pipeline(args.pipeline)
            runner = Runner(progress=True)
            run_dir = runner.run(
                pipeline,
                params,
                run_dir=args.run_dir,
                start_stage=args.from_stage,
                stop_after=args.stop_after,
                stage_only=args.stage,
                concurrency_override=args.concurrency,
            )
            print(f"run_dir: {run_dir}")
            return 0
        except (PipelineError, RunnerError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
