from app.observability.config import LangSmithSettings


def test_defaults_to_disabled():
    settings = LangSmithSettings(_env_file=None)

    assert settings.enabled is False
    assert settings.api_key is None
    assert settings.project == "ai-test-intelligence-platform"
    assert settings.endpoint is None


def test_reads_overrides_from_env_with_langsmith_prefix(monkeypatch):
    monkeypatch.setenv("LANGSMITH_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-test-not-real")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-project")

    settings = LangSmithSettings(_env_file=None)

    assert settings.enabled is True
    assert settings.api_key.get_secret_value() == "ls-test-not-real"
    assert settings.project == "my-project"


def test_api_key_is_not_exposed_in_repr(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-super-secret")

    settings = LangSmithSettings(_env_file=None)

    assert "ls-super-secret" not in repr(settings.api_key)
    assert "ls-super-secret" not in str(settings)
