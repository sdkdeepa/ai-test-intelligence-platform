"""Small representative-scenario datasets for LangSmith evaluation.

Deliberately independent of tests/fixtures/ (the exhaustive unit-test
fixtures from Sprints 6-8): this is production code, and production code
has no business importing from tests/. These are a small, curated subset —
"small evaluation datasets," not exhaustive coverage — meant for LangSmith's
dataset/evaluation UI so scenario behavior can be tracked over time as
prompts and models change.

Every function here takes an already-constructed `Client` (see
langsmith_client.py) rather than constructing its own — callers decide
whether this runs at all, and main.py's startup hook is what actually
guards it against LangSmith being disabled/unreachable.
"""

from typing import Any

from app.observability.logging import get_logger

logger = get_logger(__name__)

RISK_ANALYSIS_DATASET = "ai-test-intelligence-platform-risk-analysis"
TEST_INTELLIGENCE_DATASET = "ai-test-intelligence-platform-test-intelligence"
FAILURE_INTELLIGENCE_DATASET = "ai-test-intelligence-platform-failure-intelligence"

RISK_ANALYSIS_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "diff": (
                "diff --git a/app/auth/login.py b/app/auth/login.py\n"
                "index 111..222 100644\n"
                "--- a/app/auth/login.py\n"
                "+++ b/app/auth/login.py\n"
                "@@ -1,3 +1,3 @@\n"
                "-    if not check_password(user, password):\n"
                "+    if not authenticate(user, password):\n"
                '         raise ValueError("invalid credentials")\n'
            )
        },
        "outputs": {"expected_release_recommendation": "caution"},
        "metadata": {"scenario": "authentication_change"},
    },
    {
        "inputs": {
            "diff": (
                "diff --git a/README.md b/README.md\nindex 1..2 100644\n"
                "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n"
            )
        },
        "outputs": {"expected_release_recommendation": "proceed"},
        "metadata": {"scenario": "low_risk_docs_change"},
    },
    {
        "inputs": {
            "diff": (
                "diff --git a/backend/migrations/versions/x.py b/backend/migrations/versions/x.py\n"
                "new file mode 100644\nindex 000..111\n--- /dev/null\n+++ b/backend/migrations/versions/x.py\n"
                "@@ -0,0 +1,3 @@\n+from alembic import op\n+def upgrade():\n"
                '+    op.execute("ALTER TABLE x ADD COLUMN y")\n'
            )
        },
        "outputs": {"expected_release_recommendation": "caution"},
        "metadata": {"scenario": "schema_migration"},
    },
]

TEST_INTELLIGENCE_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {"source_code": "def add(a, b):\n    return a + b\n"},
        "outputs": {"expected_applicable_types": ["unit"]},
        "metadata": {"scenario": "unit_only_source"},
    },
    {
        "inputs": {
            "api_specification": (
                "openapi: 3.0.0\npaths:\n  /accounts/{id}:\n    get:\n      summary: Fetch an account\n"
            )
        },
        "outputs": {"expected_applicable_types": ["api", "contract", "integration"]},
        "metadata": {"scenario": "api_specification_only"},
    },
    {
        "inputs": {
            "requirement_text": "As a shopper, I want to complete checkout in a single workflow.",
            "source_code": "def checkout(cart):\n    return charge(sum(i.price for i in cart.items))\n",
        },
        "outputs": {"expected_applicable_types": ["unit", "end_to_end"]},
        "metadata": {"scenario": "requirement_text_scenario"},
    },
]

FAILURE_INTELLIGENCE_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {"pytest_output": "FAILED tests/test_math.py::test_add - AssertionError: assert 5 == 4\n"},
        "outputs": {"expected_classification": "regression"},
        "metadata": {"scenario": "assertion_failure"},
    },
    {
        "inputs": {
            "ci_log": "psycopg.OperationalError: could not connect to server: Connection refused\n",
            "application_log": "CRITICAL app.persistence.database: DATABASE_URL environment variable not set\n",
        },
        "outputs": {"expected_classification": "environment"},
        "metadata": {"scenario": "environment_configuration_issue"},
    },
    {
        "inputs": {"ci_log": "Test run exceeded the configured timeout of 30s.\n"},
        "outputs": {"expected_classification": "unknown"},
        "metadata": {"scenario": "ambiguous_timeout"},
    },
]


def sync_dataset(client: Any, dataset_name: str, examples: list[dict[str, Any]]) -> None:
    """Create `dataset_name` if missing, then add any example whose
    metadata['scenario'] isn't already present — safe to call repeatedly
    (e.g. once per app startup) without duplicating examples.

    Raises on a real LangSmith failure rather than swallowing it — the
    no-fail contract lives in the caller (main.py's startup hook wraps this
    in try/except), so a deliberate manual sync run can still see real errors.
    """
    if not client.has_dataset(dataset_name=dataset_name):
        client.create_dataset(dataset_name=dataset_name, description=f"Representative scenarios for {dataset_name}")

    existing_scenarios = {
        example.metadata.get("scenario")
        for example in client.list_examples(dataset_name=dataset_name)
        if example.metadata
    }
    for example in examples:
        scenario = example["metadata"]["scenario"]
        if scenario in existing_scenarios:
            continue
        client.create_example(
            inputs=example["inputs"],
            outputs=example.get("outputs"),
            metadata=example["metadata"],
            dataset_name=dataset_name,
        )


def sync_all_evaluation_datasets(client: Any) -> None:
    sync_dataset(client, RISK_ANALYSIS_DATASET, RISK_ANALYSIS_EXAMPLES)
    sync_dataset(client, TEST_INTELLIGENCE_DATASET, TEST_INTELLIGENCE_EXAMPLES)
    sync_dataset(client, FAILURE_INTELLIGENCE_DATASET, FAILURE_INTELLIGENCE_EXAMPLES)
    logger.info("langsmith_datasets_synced")
