from promptchain.pipeline import Pipeline, Stage
from promptchain.runner import Runner


class FakeProvider:
    def ensure_model(self, model: str) -> None:
        return None

    def generate(self, **kwargs) -> str:
        return "ok"


def test_support_files_not_in_output(tmp_path):
    stage = Stage(
        stage_id="stage_one",
        prompt="Say hello to {topic}.",
        provider="ollama",
        model="fake-model",
        reasoning_effort=None,
        temperature=None,
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

    raw_path = run_dir / "logs" / "stages" / "stage_one" / "raw.txt"
    assert raw_path.exists()

    output_dir = run_dir / "output"
    raw_in_output = list(output_dir.rglob("raw.txt"))
    assert raw_in_output == []
