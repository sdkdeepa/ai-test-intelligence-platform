from app.observability.config import LangSmithSettings
from app.observability.langsmith_client import build_client


def test_disabled_returns_none_without_touching_the_network():
    settings = LangSmithSettings(enabled=False, _env_file=None)

    assert build_client(settings) is None


def test_enabled_without_api_key_returns_none():
    settings = LangSmithSettings(enabled=True, api_key=None, _env_file=None)

    assert build_client(settings) is None


def test_enabled_with_api_key_constructs_a_client():
    """Client construction itself doesn't validate the key over the network
    (langsmith.Client is lazy) — this only proves the wiring is correct, not
    that the key is valid.
    """
    settings = LangSmithSettings(enabled=True, api_key="ls-test-not-real", _env_file=None)

    client = build_client(settings)

    assert client is not None


def test_construction_failure_is_caught_and_returns_none(monkeypatch):
    import langsmith

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(langsmith, "Client", _raise)
    settings = LangSmithSettings(enabled=True, api_key="ls-test-not-real", _env_file=None)

    assert build_client(settings) is None
