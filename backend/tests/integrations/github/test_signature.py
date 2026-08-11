from app.integrations.github.signature import compute_signature, verify_signature


def test_valid_signature_verifies():
    secret = "test-secret"
    payload = b'{"action": "opened"}'
    signature = compute_signature(secret, payload)

    assert verify_signature(secret, payload, signature) is True


def test_signature_with_wrong_secret_fails():
    payload = b'{"action": "opened"}'
    signature = compute_signature("correct-secret", payload)

    assert verify_signature("wrong-secret", payload, signature) is False


def test_signature_for_different_payload_fails():
    secret = "test-secret"
    signature = compute_signature(secret, b'{"action": "opened"}')

    assert verify_signature(secret, b'{"action": "closed"}', signature) is False


def test_missing_signature_header_fails():
    assert verify_signature("test-secret", b"{}", None) is False


def test_empty_secret_fails():
    signature = compute_signature("some-secret", b"{}")
    assert verify_signature("", b"{}", signature) is False


def test_malformed_signature_header_fails():
    assert verify_signature("test-secret", b"{}", "not-a-real-signature") is False


def test_signature_has_expected_prefix_and_length():
    signature = compute_signature("test-secret", b"{}")
    assert signature.startswith("sha256=")
    assert len(signature) == len("sha256=") + 64  # hex-encoded SHA-256 digest
