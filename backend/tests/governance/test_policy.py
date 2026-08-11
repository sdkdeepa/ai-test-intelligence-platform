from app.governance.config import GovernancePolicySettings
from app.governance.policy import evaluate_risk_policy, requires_review

_DEFAULTS = GovernancePolicySettings()

_CLEAN = {
    "risk_score": 0.1,
    "confidence_score": 0.9,
    "categories": [],
    "evidence": [],
    "release_recommendation": "proceed",
}


def test_clean_low_risk_result_triggers_nothing():
    reasons = evaluate_risk_policy(_CLEAN, settings=_DEFAULTS)
    assert reasons == []
    assert requires_review(_CLEAN, settings=_DEFAULTS) is False


def test_block_recommendation_triggers_high_release_risk():
    output = {**_CLEAN, "release_recommendation": "block", "risk_score": 0.8, "evidence": ["a finding"]}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert [r.rule for r in reasons] == ["high_release_risk"]


def test_block_can_be_disabled_via_settings():
    settings = GovernancePolicySettings(require_review_on_block=False)
    output = {**_CLEAN, "release_recommendation": "block", "risk_score": 0.2, "evidence": ["a finding"]}
    reasons = evaluate_risk_policy(output, settings=settings)
    # risk_score 0.2 is under the default 0.7 threshold, and block-review is
    # off, so nothing should trigger from the release_recommendation alone.
    assert reasons == []


def test_risk_score_above_threshold_triggers_without_block_recommendation():
    output = {**_CLEAN, "risk_score": 0.75, "release_recommendation": "caution"}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "high_release_risk" for r in reasons)


def test_risk_score_below_threshold_does_not_trigger():
    output = {**_CLEAN, "risk_score": 0.69, "release_recommendation": "caution"}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert not any(r.rule == "high_release_risk" for r in reasons)


def test_caution_does_not_trigger_by_default():
    output = {**_CLEAN, "release_recommendation": "caution", "risk_score": 0.4, "evidence": ["a finding"]}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert reasons == []


def test_caution_triggers_when_enabled():
    settings = GovernancePolicySettings(require_review_on_caution=True)
    output = {**_CLEAN, "release_recommendation": "caution", "risk_score": 0.4}
    reasons = evaluate_risk_policy(output, settings=settings)
    assert any(r.rule == "elevated_release_risk" for r in reasons)


def test_low_confidence_triggers():
    output = {**_CLEAN, "confidence_score": 0.3}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "low_confidence" for r in reasons)


def test_confidence_at_threshold_does_not_trigger():
    output = {**_CLEAN, "confidence_score": _DEFAULTS.confidence_threshold}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert not any(r.rule == "low_confidence" for r in reasons)


def test_authentication_category_triggers():
    output = {**_CLEAN, "categories": ["authentication_authorization"]}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "authentication_or_authorization_change" for r in reasons)


def test_security_sensitive_category_triggers():
    output = {**_CLEAN, "categories": ["security_sensitive_file"]}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "security_sensitive_finding" for r in reasons)


def test_breaking_change_categories_trigger():
    for category in ("api_contract", "schema_database"):
        output = {**_CLEAN, "categories": [category]}
        reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
        assert any(r.rule == "breaking_api_or_schema_change" for r in reasons), category


def test_unrelated_categories_do_not_trigger():
    output = {**_CLEAN, "categories": ["dependency", "configuration", "retry_timeout", "error_handling"]}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert reasons == []


def test_insufficient_evidence_does_not_trigger_for_a_clean_proceed_result():
    """A genuinely clean result (proceed, low score) has nothing to cite
    evidence for — empty evidence there means "nothing flagged", not "an
    unsupported claim". See policy.py's inline comment for the rationale.
    """
    output = {**_CLEAN, "evidence": []}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert not any(r.rule == "insufficient_evidence" for r in reasons)


def test_insufficient_evidence_triggers_when_release_recommendation_is_not_proceed():
    output = {**_CLEAN, "release_recommendation": "caution", "evidence": [], "risk_score": 0.4}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "insufficient_evidence" for r in reasons)


def test_insufficient_evidence_triggers_when_risk_score_is_high_even_if_proceed():
    output = {**_CLEAN, "release_recommendation": "proceed", "evidence": [], "risk_score": 0.9}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert any(r.rule == "insufficient_evidence" for r in reasons)


def test_sufficient_evidence_does_not_trigger():
    output = {**_CLEAN, "release_recommendation": "caution", "evidence": ["one finding"], "risk_score": 0.4}
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    assert not any(r.rule == "insufficient_evidence" for r in reasons)


def test_multiple_rules_can_trigger_simultaneously():
    output = {
        "risk_score": 0.9,
        "confidence_score": 0.1,
        "categories": ["authentication_authorization", "security_sensitive_file"],
        "evidence": [],
        "release_recommendation": "block",
    }
    reasons = evaluate_risk_policy(output, settings=_DEFAULTS)
    rule_names = {r.rule for r in reasons}
    assert "high_release_risk" in rule_names
    assert "low_confidence" in rule_names
    assert "authentication_or_authorization_change" in rule_names
    assert "security_sensitive_finding" in rule_names
    assert len(reasons) >= 4


def test_disabled_settings_short_circuit_to_no_reasons():
    settings = GovernancePolicySettings(enabled=False)
    output = {
        "risk_score": 0.99,
        "confidence_score": 0.0,
        "categories": ["authentication_authorization"],
        "evidence": [],
        "release_recommendation": "block",
    }
    assert evaluate_risk_policy(output, settings=settings) == []
    assert requires_review(output, settings=settings) is False


def test_missing_fields_default_to_safe_values():
    """A risk output dict missing keys entirely (rather than having them
    explicitly set to defaults) must not crash policy evaluation.
    """
    reasons = evaluate_risk_policy({}, settings=_DEFAULTS)
    assert reasons == []
