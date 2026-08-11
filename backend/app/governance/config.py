from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GovernancePolicySettings(BaseSettings):
    """Configurable thresholds for `governance/policy.py`'s review-required
    rules, sourced from environment variables / .env — kept separate from
    the root app Settings, same rationale as `providers/config.py` and
    `integrations/github/config.py` (architecture.md §5: each self-contained
    module owns its own settings).

    The rule *taxonomy* (which risk categories count as "security-sensitive"
    vs. "breaking change") is a fixed mapping onto the Risk Engine's actual
    category vocabulary (`analysis/risk/heuristics.py`'s `category=...`
    values) and lives in `policy.py` as module constants, not here — env-var
    lists are awkward to configure correctly (JSON-in-an-env-string) and the
    category vocabulary is an engine-internal contract, not an operator
    tuning knob. What operators actually need to tune are the *numeric*
    thresholds and *whether* a given rule applies at all, which is exactly
    what's exposed below.
    """

    enabled: bool = True  # global kill-switch — False means every review is auto-approved (see policy.py)

    risk_score_threshold: float = 0.7  # risk_score >= this triggers "high_release_risk"
    confidence_threshold: float = 0.5  # confidence_score < this triggers "low_confidence"
    min_evidence_count: int = 1  # fewer than this triggers "insufficient_evidence"

    require_review_on_block: bool = True  # release_recommendation == "block"
    require_review_on_caution: bool = False  # release_recommendation == "caution" — off by default,
    # since caution is meant to be a softer signal than block (see
    # integrations/github/comment.py's commit_status_state docstring for the
    # same "caution shouldn't hard-gate by default" reasoning) — an operator
    # who wants stricter gating can flip this on.

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GOVERNANCE_", extra="ignore")


@lru_cache
def get_governance_settings() -> GovernancePolicySettings:
    return GovernancePolicySettings()
