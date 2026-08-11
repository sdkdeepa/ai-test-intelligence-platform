"""GitHub webhook HMAC-SHA256 signature verification.

GitHub signs every webhook delivery with the shared secret configured on the
webhook (docs: https://docs.github.com/webhooks/using-webhooks/validating-webhook-deliveries),
sent as `X-Hub-Signature-256: sha256=<hexdigest>` over the *raw* request
body. Verification must happen against those exact raw bytes — parsing to
JSON first and re-serializing would not reproduce the same signature (key
order, whitespace, and number formatting aren't guaranteed to round-trip).
"""

import hashlib
import hmac

_SIGNATURE_PREFIX = "sha256="


def compute_signature(secret: str, payload: bytes) -> str:
    """The `sha256=<hexdigest>` value GitHub would send for `payload` signed
    with `secret` — used by verify_signature and by tests building fixture
    requests.
    """
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """True iff `signature_header` is a valid `X-Hub-Signature-256` value for
    `payload` signed with `secret`.

    Uses `hmac.compare_digest` (constant-time) rather than `==` — a
    timing-based comparison would leak how many leading bytes of a guessed
    signature were correct, letting an attacker forge a valid one byte at a
    time.
    """
    if not signature_header or not secret:
        return False
    expected = compute_signature(secret, payload)
    return hmac.compare_digest(expected, signature_header)
