import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def load_webhook_payload(name: str) -> dict:
    """Read a GitHub webhook payload fixture (tests/fixtures/github/*.json)
    by name, no extension — mirrors tests/fixtures/loader.py's
    `load_diff_fixture` for the equivalent diff fixtures.
    """
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text())
