import pytest

from app.ingestion.github_webhook import (
    MalformedWebhookPayloadError,
    parse_pull_request_event,
)
from tests.fixtures.github.loader import load_webhook_payload


def test_parses_opened_event():
    payload = load_webhook_payload("pull_request_opened")
    event = parse_pull_request_event(payload)

    assert event is not None
    assert event.action == "opened"
    assert event.owner == "acme"
    assert event.repo_name == "widgets"
    assert event.repo_url == "https://github.com/acme/widgets"
    assert event.pr_number == 42
    assert event.head_sha == "abc123def456"
    assert event.base_sha == "111222333444"
    assert event.full_name == "acme/widgets"


def test_opened_and_synchronize_are_relevant():
    for name in ("pull_request_opened", "pull_request_synchronize"):
        event = parse_pull_request_event(load_webhook_payload(name))
        assert event is not None
        assert event.is_relevant is True


def test_closed_is_not_relevant():
    event = parse_pull_request_event(load_webhook_payload("pull_request_closed"))
    assert event is not None
    assert event.is_relevant is False


def test_non_pull_request_payload_returns_none():
    assert parse_pull_request_event({"action": "created", "issue": {}}) is None


def test_missing_repository_key_returns_none():
    assert parse_pull_request_event({"action": "opened", "pull_request": {}}) is None


def test_malformed_pull_request_payload_raises():
    payload = load_webhook_payload("pull_request_malformed")
    with pytest.raises(MalformedWebhookPayloadError):
        parse_pull_request_event(payload)
