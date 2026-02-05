import json

from promptchain.pipeline import Pipeline, Stage
from promptchain.runner import Runner


class FakeProvider:
    def ensure_model(self, model: str) -> None:
        return None

    def generate(self, **kwargs) -> str:
        return "ok"


def test_stage_meta_records_reasoning_effort(tmp_path):
    stage = Stage(
        stage_id="stage_one",
        prompt="Say hello to {topic}.",
        provider="ollama",
        model="fake-model",
        reasoning_effort="high",
        temperature=0.2,
        enabled=True,
        concurrency_enabled=False,
        concurrency_max_in_flight=None,
        batch_enabled=False,
        output="markdown",
        mode="single",
        map_from=None,
        map_from_file=None,
        publish=True,
        input_files={},
    )
    pipeline = Pipeline(
        name="test_pipeline",
        provider="ollama",
        model="fake-model",
        reasoning_effort=None,
        temperature=None,
        stages=[stage],
        path="pipeline.yml",
    )
    runner = Runner(runs_root=tmp_path)
    runner._providers["ollama"] = FakeProvider()

    run_dir = runner.run(pipeline, {"topic": "world"})
    stage_meta = json.loads((run_dir / "stages" / "stage_one" / "stage.json").read_text())

    assert stage_meta["reasoning_effort"] == "high"
    assert stage_meta["temperature"] == 0.2
