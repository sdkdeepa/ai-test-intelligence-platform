from pathlib import Path

DIFFS_DIR = Path(__file__).parent / "diffs"


def load_diff_fixture(name: str) -> str:
    """Read a `.diff` fixture from tests/fixtures/diffs/ by name (no extension)."""
    return (DIFFS_DIR / f"{name}.diff").read_text()


def list_diff_fixture_names() -> list[str]:
    return sorted(path.stem for path in DIFFS_DIR.glob("*.diff"))
