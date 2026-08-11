"""Sensitive-data redaction — Sprint 13's requirement that secrets never
reach an LLM provider or get written into the audit trail unredacted.

Deliberately pattern-based over *values* (AWS keys, bearer tokens, PEM
key blocks, assigned password/secret literals), not over *identifiers*
(the word "password", "authenticate", "secret" as a variable/function name).
That distinction matters: `analysis/risk/heuristics.py` and
`analysis/test_intelligence/heuristics.py` detect risk/test signals by
matching exactly those identifier keywords in code — if redaction blanked
out every occurrence of the word "password", it would silently defeat the
platform's own risk detection. Redaction here only ever removes things that
look like actual secret *material*, never the surrounding code structure or
keywords engines depend on.

Two call sites (see module docstring cross-references below):
- `AnalysisOrchestrator.submit()` redacts every string value in `inputs`
  before building `AnalysisContext` — i.e. before the diff text an engine
  will embed into an LLM prompt ever reaches the engine at all. Generic,
  not risk-specific: every engine benefits automatically.
- `governance/review_service.py` redacts every string value in an
  `AuditEvent.payload` dict before insert — the audit trail is a permanent,
  queryable record, so it gets the same treatment independently (an
  `AuditEvent` can be constructed from data that never went through
  `submit()`, e.g. a human reviewer's free-text `review_reason`).
"""

import re

_REDACTED = "[REDACTED]"

# Each pattern targets a recognizable secret *shape*, not a keyword. Order
# matters only in that more specific patterns (PEM blocks) run before
# generic ones (long base64-ish tokens) so a PEM block isn't left partially
# redacted by a broader pattern matching inside it first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "pem_private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    ),
    ("aws_access_key_id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret_access_key", re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*")),
    (
        "generic_secret_assignment",
        # `password = "..."`, `api_key: '...'`, `secret="..."` etc. — an
        # identifier containing password/secret/token/api_key immediately
        # followed by an assignment and a quoted literal. Only the quoted
        # *value* is replaced; the identifier itself (which heuristics.py's
        # security detectors rely on) is left untouched.
        re.compile(r"(?i)\b((?:api[_-]?key|secret|password|passwd|token|access[_-]?key)\w*\s*[:=]\s*)(['\"])(.*?)\2"),
    ),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
]


def redact(text: str) -> str:
    """Replace recognizable secret material in `text` with `[REDACTED]`.
    Structure-preserving (line count, surrounding code) except for the PEM
    block case, where the entire multi-line block collapses to one
    placeholder line — correct behavior for a key block, not a bug: leaving
    even partial key material recognizable defeats the point.
    """
    if not text:
        return text

    result = text
    for name, pattern in _PATTERNS:
        if name == "generic_secret_assignment":
            result = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}{m.group(2)}", result)
        else:
            result = pattern.sub(_REDACTED, result)
    return result


def redact_payload(value: object) -> object:
    """Recursively redact every string found in `value` — used for
    `AuditEvent.payload` dicts, which can nest lists/dicts of strings
    (e.g. `{"reasons": [...], "risk_summary": {"evidence": [...]}}`).
    Non-string, non-container values (numbers, bools, None, UUIDs) pass
    through unchanged.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(v) for v in value)
    return value
