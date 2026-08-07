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


def test_anthropic_api_key_defaults_to_none():
    settings = ProviderSettings(_env_file=None)

    assert settings.anthropic_api_key is None
    assert settings.anthropic_model == "claude-sonnet-5"
    assert settings.anthropic_max_tokens == 1024
    assert settings.anthropic_timeout == 60.0
    assert settings.anthropic_max_retries == 2


def test_anthropic_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("PROVIDER_ANTHROPIC_MODEL", "claude-opus-5")
    monkeypatch.setenv("PROVIDER_ANTHROPIC_MAX_TOKENS", "2048")
    monkeypatch.setenv("PROVIDER_ANTHROPIC_TIMEOUT", "15")
    monkeypatch.setenv("PROVIDER_ANTHROPIC_MAX_RETRIES", "5")

    settings = ProviderSettings(_env_file=None)

    assert settings.anthropic_api_key.get_secret_value() == "sk-test-not-real"
    assert settings.anthropic_model == "claude-opus-5"
    assert settings.anthropic_max_tokens == 2048
    assert settings.anthropic_timeout == 15.0
    assert settings.anthropic_max_retries == 5


def test_anthropic_api_key_is_not_exposed_in_repr(monkeypatch):
    monkeypatch.setenv("PROVIDER_ANTHROPIC_API_KEY", "sk-super-secret")

    settings = ProviderSettings(_env_file=None)

    assert "sk-super-secret" not in repr(settings.anthropic_api_key)
    assert "sk-super-secret" not in str(settings)
