from dataclasses import dataclass

from app.observability import eval_datasets


@dataclass
class _FakeExample:
    metadata: dict


class _FakeLangSmithClient:
    """Minimal double covering just the Client methods sync_dataset() calls,
    since there's no real LangSmith server to test against in CI.
    """

    def __init__(self):
        self.datasets: set[str] = set()
        self.examples: dict[str, list[_FakeExample]] = {}
        self.create_dataset_calls: list[str] = []
        self.create_example_calls: list[dict] = []

    def has_dataset(self, *, dataset_name: str) -> bool:
        return dataset_name in self.datasets

    def create_dataset(self, *, dataset_name: str, description: str | None = None):
        self.datasets.add(dataset_name)
        self.examples.setdefault(dataset_name, [])
        self.create_dataset_calls.append(dataset_name)

    def list_examples(self, *, dataset_name: str):
        return list(self.examples.get(dataset_name, []))

    def create_example(self, *, inputs, outputs, metadata, dataset_name):
        self.examples.setdefault(dataset_name, []).append(_FakeExample(metadata=metadata))
        self.create_example_calls.append({"dataset_name": dataset_name, "metadata": metadata})


def test_datasets_cover_all_three_engines():
    assert eval_datasets.RISK_ANALYSIS_EXAMPLES
    assert eval_datasets.TEST_INTELLIGENCE_EXAMPLES
    assert eval_datasets.FAILURE_INTELLIGENCE_EXAMPLES


def test_every_example_has_a_unique_scenario_name():
    for examples in (
        eval_datasets.RISK_ANALYSIS_EXAMPLES,
        eval_datasets.TEST_INTELLIGENCE_EXAMPLES,
        eval_datasets.FAILURE_INTELLIGENCE_EXAMPLES,
    ):
        scenarios = [e["metadata"]["scenario"] for e in examples]
        assert len(scenarios) == len(set(scenarios))


def test_sync_dataset_creates_the_dataset_if_missing():
    client = _FakeLangSmithClient()

    eval_datasets.sync_dataset(client, "my-dataset", eval_datasets.RISK_ANALYSIS_EXAMPLES)

    assert client.has_dataset(dataset_name="my-dataset")
    assert len(client.create_example_calls) == len(eval_datasets.RISK_ANALYSIS_EXAMPLES)


def test_sync_dataset_does_not_duplicate_existing_scenarios():
    client = _FakeLangSmithClient()
    eval_datasets.sync_dataset(client, "my-dataset", eval_datasets.RISK_ANALYSIS_EXAMPLES)

    eval_datasets.sync_dataset(client, "my-dataset", eval_datasets.RISK_ANALYSIS_EXAMPLES)

    assert len(client.create_example_calls) == len(eval_datasets.RISK_ANALYSIS_EXAMPLES)  # not doubled


def test_sync_dataset_skips_dataset_creation_if_already_present():
    client = _FakeLangSmithClient()
    client.datasets.add("already-there")

    eval_datasets.sync_dataset(client, "already-there", eval_datasets.TEST_INTELLIGENCE_EXAMPLES)

    assert client.create_dataset_calls == []


def test_sync_all_evaluation_datasets_covers_all_three():
    client = _FakeLangSmithClient()

    eval_datasets.sync_all_evaluation_datasets(client)

    assert client.has_dataset(dataset_name=eval_datasets.RISK_ANALYSIS_DATASET)
    assert client.has_dataset(dataset_name=eval_datasets.TEST_INTELLIGENCE_DATASET)
    assert client.has_dataset(dataset_name=eval_datasets.FAILURE_INTELLIGENCE_DATASET)
