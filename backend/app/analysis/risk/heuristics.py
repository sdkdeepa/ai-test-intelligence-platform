"""Deterministic risk signal detection and scoring.

This module is the "don't rely only on the LLM" half of the Risk Engine: it
never calls a provider, is fully deterministic (same diff in, same
assessment out), and produces the risk_score, categories, evidence,
affected_components, recommended_regression_scope, and release_recommendation
on its own. `engine.py` layers a Claude-generated narrative and a bounded
confidence adjustment on top of this — see its module docstring for how the
two are combined.
"""

import re
from dataclasses import dataclass

from app.ingestion.diff import GitDiff

RISK_CATEGORIES: tuple[str, ...] = (
    "authentication_authorization",
    "api_contract",
    "schema_database",
    "dependency",
    "configuration",
    "retry_timeout",
    "error_handling",
    "security_sensitive_file",
)

# Release-recommendation thresholds on the final (deterministic + LLM
# confidence-adjusted) risk_score. Deliberately simple and inspectable
# rather than another model — this *is* the policy, not a placeholder for one.
_BLOCK_THRESHOLD = 0.7
_CAUTION_THRESHOLD = 0.35

_BASELINE_REGRESSION_SCOPE = "Unit tests for all directly changed files"

_REGRESSION_SCOPE_BY_CATEGORY: dict[str, str] = {
    "authentication_authorization": (
        "Full authentication/authorization regression suite, including session and permission edge cases"
    ),
    "api_contract": "Contract tests for all consumers of the changed endpoint(s); verify backward compatibility",
    "schema_database": "Migration up/down tests plus data-integrity checks against a production-like dataset",
    "dependency": "Full integration test suite; check the updated dependency's changelog for breaking changes",
    "configuration": "Deploy to a staging environment and verify startup with the new configuration",
    "retry_timeout": "Failure-injection tests (timeouts, transient errors) to confirm retry/backoff behaves as intended",
    "error_handling": "Negative-path tests for every changed error branch",
    "security_sensitive_file": "Security review of the changed file's access controls and secret handling",
}


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


@dataclass(frozen=True)
class _HeuristicRule:
    category: str
    weight: float
    description: str
    file_path_pattern: re.Pattern | None = None
    content_pattern: re.Pattern | None = None


_RULES: tuple[_HeuristicRule, ...] = (
    _HeuristicRule(
        category="authentication_authorization",
        weight=0.9,
        description="file path suggests authentication/authorization logic",
        file_path_pattern=_rx(r"(auth|login|session|permission|rbac|acl)"),
    ),
    _HeuristicRule(
        category="authentication_authorization",
        weight=0.85,
        description="added/removed lines reference authentication/authorization primitives",
        content_pattern=_rx(
            r"\b(authenticate|authorize|jwt|password|is_admin|login_required"
            r"|permission_required|access_token|refresh_token)\b"
        ),
    ),
    _HeuristicRule(
        category="api_contract",
        weight=0.75,
        description="file path suggests an API route/endpoint definition",
        file_path_pattern=_rx(r"(api/|routes?/|endpoints?/)"),
    ),
    _HeuristicRule(
        category="api_contract",
        weight=0.7,
        description="added/removed lines change a route decorator or response model",
        content_pattern=_rx(r"(@(app|router)\.(get|post|put|patch|delete)|response_model\s*=|APIRouter\()"),
    ),
    _HeuristicRule(
        category="schema_database",
        weight=0.85,
        description="file path suggests a schema/model/migration change",
        file_path_pattern=_rx(r"(models?\.py$|migrations?/|schema|\.sql$|alembic)"),
    ),
    _HeuristicRule(
        category="schema_database",
        weight=0.8,
        description="added/removed lines contain DDL or ORM schema definitions",
        content_pattern=_rx(r"(create\s+table|alter\s+table|drop\s+table|mapped_column|declarative_base|foreignkey\()"),
    ),
    _HeuristicRule(
        category="dependency",
        weight=0.55,
        description="file path is a dependency manifest",
        file_path_pattern=_rx(
            r"(pyproject\.toml$|requirements.*\.txt$|package\.json$|poetry\.lock$"
            r"|package-lock\.json$|Pipfile$|go\.mod$|Gemfile$)"
        ),
    ),
    _HeuristicRule(
        category="configuration",
        weight=0.45,
        description="file path is an application/deployment configuration file",
        file_path_pattern=_rx(r"(\.env|config\.py$|settings\.py$|docker-compose.*\.ya?ml$|Dockerfile$|\.ya?ml$)"),
    ),
    _HeuristicRule(
        category="retry_timeout",
        weight=0.5,
        description="added/removed lines reference retry/backoff/timeout behavior",
        content_pattern=_rx(r"\b(retry|retries|backoff|timeout|max_retries)\b"),
    ),
    _HeuristicRule(
        category="error_handling",
        weight=0.45,
        description="added/removed lines change error handling",
        content_pattern=_rx(r"(\bexcept\s|\braise\s|HTTPException|\btry:|\bcatch\s*\()"),
    ),
    _HeuristicRule(
        category="security_sensitive_file",
        weight=0.85,
        description="file path is security-sensitive (secrets/credentials/keys)",
        file_path_pattern=_rx(r"(secret|credential|\.pem$|\.key$|id_rsa|\.env$)"),
    ),
    _HeuristicRule(
        category="security_sensitive_file",
        weight=0.6,
        description="added/removed lines reference secret-like values",
        content_pattern=_rx(r"\b(api_key|secret_key|private_key)\b|password\s*="),
    ),
)


@dataclass(frozen=True)
class Signal:
    category: str
    file_path: str
    weight: float
    detail: str


def detect_signals(diff: GitDiff) -> list[Signal]:
    signals: list[Signal] = []
    for file in diff.files:
        content = "\n".join(file.all_changed_lines)
        for rule in _RULES:
            matched = bool(rule.file_path_pattern and rule.file_path_pattern.search(file.path))
            if not matched and rule.content_pattern and content:
                matched = bool(rule.content_pattern.search(content))
            if matched:
                signals.append(
                    Signal(category=rule.category, file_path=file.path, weight=rule.weight, detail=rule.description)
                )
    return signals


@dataclass(frozen=True)
class DeterministicAssessment:
    risk_score: float
    categories: list[str]
    evidence: list[str]
    confidence_score: float
    affected_components: list[str]
    recommended_regression_scope: list[str]
    release_recommendation: str
    primary_file: str
    signals: list[Signal]


def _component_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def _release_recommendation(risk_score: float) -> str:
    if risk_score >= _BLOCK_THRESHOLD:
        return "block"
    if risk_score >= _CAUTION_THRESHOLD:
        return "caution"
    return "proceed"


def compute_deterministic_assessment(diff: GitDiff) -> DeterministicAssessment:
    signals = detect_signals(diff)

    # Size-based baseline: even pattern-free diffs carry some risk once
    # they're large, capped low so it never dominates an actual signal match.
    baseline = min(0.3, 0.01 * diff.total_changed_lines)

    category_weight: dict[str, float] = {}
    for signal in signals:
        category_weight[signal.category] = max(category_weight.get(signal.category, 0.0), signal.weight)

    # Independent-OR combination: each triggered category multiplies down the
    # "safe" probability, so multiple signals compound risk without a naive
    # sum overshooting 1.0.
    safe_probability = 1.0
    for weight in category_weight.values():
        safe_probability *= 1.0 - weight
    category_risk = 1.0 - safe_probability

    risk_score = round(min(1.0, baseline + category_risk * (1.0 - baseline)), 4)
    categories = sorted(category_weight)
    evidence = [f"{s.category}: {s.file_path} — {s.detail}" for s in signals]

    if diff.files:
        confidence_score = round(min(0.95, 0.55 + 0.1 * len(categories)), 4)
    else:
        confidence_score = 0.3  # nothing to assess

    affected_components = sorted({_component_of(p) for p in diff.changed_paths})

    if categories:
        recommended_regression_scope = [_BASELINE_REGRESSION_SCOPE] + [
            _REGRESSION_SCOPE_BY_CATEGORY[c] for c in categories
        ]
    else:
        recommended_regression_scope = [_BASELINE_REGRESSION_SCOPE]

    if signals:
        primary_file = max(signals, key=lambda s: s.weight).file_path
    elif diff.files:
        primary_file = diff.files[0].path
    else:
        primary_file = "(no changes)"

    return DeterministicAssessment(
        risk_score=risk_score,
        categories=categories,
        evidence=evidence,
        confidence_score=confidence_score,
        affected_components=affected_components,
        recommended_regression_scope=recommended_regression_scope,
        release_recommendation=_release_recommendation(risk_score),
        primary_file=primary_file,
        signals=signals,
    )
