import json
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"


def load_failure_intelligence_fixture(name: str) -> dict:
    """Read a `.json` fixture from tests/fixtures/failure_intelligence/cases/
    by name (no extension). Keys match FailureIntelligenceInputs fields.
    """
    return json.loads((CASES_DIR / f"{name}.json").read_text())


def list_failure_intelligence_fixture_names() -> list[str]:
    return sorted(path.stem for path in CASES_DIR.glob("*.json"))
