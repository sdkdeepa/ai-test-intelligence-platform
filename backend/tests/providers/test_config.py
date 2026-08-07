from app.providers.config import ProviderSettings


def test_defaults_to_mock_provider():
    settings = ProviderSettings(_env_file=None)

    assert settings.default_provider == "mock"
    assert settings.risk_provider is None
    assert settings.generation_provider is None
    assert settings.triage_provider is None


def test_reads_overrides_from_env_with_provider_prefix(monkeypatch):
    monkeypatch.setenv("PROVIDER_DEFAULT_PROVIDER", "anthropic")
    monkeypatch.setenv("PROVIDER_TRIAGE_PROVIDER", "mock")

    settings = ProviderSettings(_env_file=None)

    assert settings.default_provider == "anthropic"
    assert settings.triage_provider == "mock"
