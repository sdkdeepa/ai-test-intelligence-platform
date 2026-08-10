"""Deterministic test-type applicability detection.

Mirrors analysis/risk/heuristics.py's "don't rely only on the LLM" design,
adapted to a different question: not "how risky is this diff" but "which
kinds of tests are plausibly relevant given what was supplied." Never calls
a provider, fully deterministic. `engine.py` layers Claude on top to
generate the actual proposed test content per applicable type — this module
only decides *which* types apply and *why*.
"""

import re
from dataclasses import dataclass

from app.analysis.test_intelligence.inputs import TestIntelligenceInputs

TEST_TYPES: tuple[str, ...] = (
    "unit",
    "api",
    "contract",
    "integration",
    "end_to_end",
    "boundary",
    "negative",
    "security",
)

FOLLOW_UP_BY_TYPE: dict[str, str] = {
    "unit": "Run the suggested test locally (pytest) and confirm it fails before the change and passes after.",
    "api": "Execute against a running instance (or TestClient) and verify response status/schema.",
    "contract": "Validate against the published API schema / consumer contract, not just this codebase's view of it.",
    "integration": "Run against real (or containerized) collaborators, not mocks, before trusting the result.",
    "end_to_end": "Run the full scenario in a staging environment mirroring production.",
    "boundary": "Confirm behavior at the exact boundary values, not just typical inputs.",
    "negative": "Confirm the system fails safely (no crash, correct error surfaced) for every invalid input tried.",
    "security": "Have a security-focused reviewer confirm the test exercises the intended access-control boundary.",
}


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


_API_CODE_RX = _rx(r"(@(app|router)\.(get|post|put|patch|delete)|APIRouter\(|response_model\s*=)")
_API_PATH_RX = _rx(r"(api/|routes?/|endpoints?/)")
_CONTRACT_RX = _rx(r"(response_model\s*=|\(BaseModel\)|openapi|paths:|components:)")
_INTEGRATION_PROSE_RX = _rx(r"\bintegration\b")
_E2E_PROSE_RX = _rx(r"\b(user|scenario|workflow|end-to-end|e2e)\b")
_BOUNDARY_RX = _rx(r"(range\(|len\(|\[0\]|\[-1\]|<=|>=|\bmin\(|\bmax\(|\bindex\b)")
_NEGATIVE_CODE_RX = _rx(r"(\bexcept\s|\braise\s|HTTPException|\btry:|ValueError|TypeError)")
_NEGATIVE_PROSE_RX = _rx(r"\b(must not|should fail|invalid|reject|not allowed)\b")
_SECURITY_CODE_RX = _rx(r"\b(authenticate|authorize|jwt|password|permission|secret|api_key)\b")
_SECURITY_PROSE_RX = _rx(r"\b(auth|permission|security|unauthorized|access control)\b")


@dataclass(frozen=True)
class Signal:
    test_type: str
    detail: str


def _detect_unit(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    if code.strip():
        return [Signal("unit", "source/diff content was supplied")]
    return []


def _detect_api(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    if inputs.api_specification:
        signals.append(Signal("api", "an API specification was supplied"))
    if _API_CODE_RX.search(code):
        signals.append(Signal("api", "code defines or changes a route or response model"))
    if inputs.file_path and _API_PATH_RX.search(inputs.file_path):
        signals.append(Signal("api", "file path suggests an API route module"))
    return signals


def _detect_contract(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    if inputs.api_specification:
        signals.append(Signal("contract", "an API specification was supplied to validate against"))
    if _CONTRACT_RX.search(code) or _CONTRACT_RX.search(prose):
        signals.append(Signal("contract", "request/response schema definitions detected"))
    return signals


def _detect_integration(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    diff = inputs.parsed_diff
    if diff is not None and len(diff.files) >= 2:
        signals.append(Signal("integration", f"diff spans {len(diff.files)} files"))
    if inputs.api_specification:
        signals.append(Signal("integration", "an API specification implies cross-component request handling"))
    if _INTEGRATION_PROSE_RX.search(prose):
        signals.append(Signal("integration", "existing test context / requirements mention integration"))
    return signals


def _detect_end_to_end(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    if inputs.requirement_text:
        signals.append(Signal("end_to_end", "requirement text describes user-facing behavior"))
    if _E2E_PROSE_RX.search(prose):
        signals.append(Signal("end_to_end", "prose mentions a user scenario or workflow"))
    return signals


def _detect_boundary(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    if _BOUNDARY_RX.search(code):
        return [Signal("boundary", "code contains range/length/index arithmetic")]
    return []


def _detect_negative(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    if _NEGATIVE_CODE_RX.search(code):
        signals.append(Signal("negative", "code contains error-handling branches"))
    if _NEGATIVE_PROSE_RX.search(prose):
        signals.append(Signal("negative", "requirements describe invalid or rejected input handling"))
    return signals


def _detect_security(inputs: TestIntelligenceInputs, code: str, prose: str) -> list[Signal]:
    signals = []
    if _SECURITY_CODE_RX.search(code):
        signals.append(Signal("security", "code references authentication/authorization/secret handling"))
    if _SECURITY_PROSE_RX.search(prose):
        signals.append(Signal("security", "requirements/spec mention auth or access control"))
    return signals


_DETECTORS = (
    _detect_unit,
    _detect_api,
    _detect_contract,
    _detect_integration,
    _detect_end_to_end,
    _detect_boundary,
    _detect_negative,
    _detect_security,
)


@dataclass(frozen=True)
class TestTypeApplicability:
    test_type: str
    applicable: bool
    evidence: list[str]
    confidence: float
    follow_up: str


def compute_applicability(inputs: TestIntelligenceInputs) -> list[TestTypeApplicability]:
    code = inputs.code_content
    prose = inputs.prose_content

    signals_by_type: dict[str, list[Signal]] = {t: [] for t in TEST_TYPES}
    for detector in _DETECTORS:
        for signal in detector(inputs, code, prose):
            signals_by_type[signal.test_type].append(signal)

    results = []
    for test_type in TEST_TYPES:
        signals = signals_by_type[test_type]
        applicable = bool(signals)
        confidence = round(min(0.9, 0.5 + 0.15 * len(signals)), 4) if applicable else 0.0
        results.append(
            TestTypeApplicability(
                test_type=test_type,
                applicable=applicable,
                evidence=[s.detail for s in signals],
                confidence=confidence,
                follow_up=FOLLOW_UP_BY_TYPE[test_type],
            )
        )
    return results


def compute_input_gaps(inputs: TestIntelligenceInputs) -> list[str]:
    """Deterministic uncovered_risks stemming purely from missing inputs —
    applies to the run overall, not any one test type.
    """
    gaps = []
    if not inputs.requirement_text:
        gaps.append(
            "No requirement text supplied — suggestions are based on code structure only and may miss intended behavior."
        )
    if not inputs.existing_test_context:
        gaps.append("Existing test coverage unknown — suggestions may duplicate coverage that already exists.")
    if not inputs.api_specification and not inputs.diff and not inputs.source_code:
        gaps.append("No code, diff, or API specification supplied — suggestions are speculative.")
    return gaps
