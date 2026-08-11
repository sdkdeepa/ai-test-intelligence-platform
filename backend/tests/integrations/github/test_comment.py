from app.integrations.github.comment import (
    build_commit_status_description,
    build_pr_comment,
    build_risk_comment,
    build_test_intelligence_comment,
    commit_status_state,
)

_RISK_OUTPUT = {
    "risk_score": 0.72,
    "release_recommendation": "block",
    "categories": ["authentication", "error_handling"],
    "evidence": [
        "authentication: app/auth/login.py — password check replaced",
        "error_handling: app/auth/login.py — bare except added",
        "error_handling: app/api/users.py — new try/except block",
    ],
    "affected_components": ["app/auth", "app/api"],
    "rationale": "A very long multi-paragraph narrative that a real Claude "
    "response would contain, full of specific reasoning that should never "
    "end up verbatim in a GitHub PR comment because it is full model output.",
}

_TEST_OUTPUT = {
    "test_suggestion_ids": ["id-1", "id-2", "id-3"],
    "suggestions": [
        {
            "test_type": "unit",
            "proposed_test": "def test_x():\n    ...full generated source spanning many lines...",
            "rationale": (
                "This is a long multi-sentence rationale that a real Claude response would produce, "
                "explaining in detail why this particular unit test matters, walking through the "
                "control flow, and generally being far too long to ever post into a GitHub PR comment."
            ),
            "evidence": ["source/diff content was supplied"],
            "assumptions": ["Assumes the supplied code reflects the final version to be tested."],
            "confidence": 0.82,
        },
        {
            "test_type": "unit",
            "proposed_test": "def test_y():\n    ...more generated source...",
            "rationale": "Another long rationale paragraph that should never appear verbatim in the comment.",
            "evidence": ["code defines or changes a route or response model"],
            "assumptions": [],
            "confidence": 0.71,
        },
        {
            "test_type": "negative",
            "proposed_test": "def test_z():\n    ...even more generated source...",
            "rationale": "Yet another long rationale paragraph that should never appear verbatim either.",
            "evidence": ["code references authentication/authorization/secret handling"],
            "assumptions": [],
            "confidence": 0.65,
        },
    ],
}


def test_commit_status_state_maps_block_to_failure():
    assert commit_status_state("block") == "failure"


def test_commit_status_state_maps_proceed_and_caution_to_success():
    assert commit_status_state("proceed") == "success"
    assert commit_status_state("caution") == "success"


def test_commit_status_description_stays_within_github_140_char_limit():
    description = build_commit_status_description(_RISK_OUTPUT)
    assert len(description) <= 140


def test_commit_status_description_includes_score_and_label():
    description = build_commit_status_description(_RISK_OUTPUT)
    assert "0.72" in description
    assert "HIGH" in description


def test_risk_comment_includes_overall_risk_and_link():
    comment = build_risk_comment(repo_id="repo-1", risk_output=_RISK_OUTPUT, platform_url="https://platform.example")
    assert "HIGH" in comment
    assert "0.72" in comment
    assert "https://platform.example/repositories/repo-1/risk" in comment


def test_risk_comment_caps_findings_and_notes_remainder():
    comment = build_risk_comment(repo_id="repo-1", risk_output=_RISK_OUTPUT, platform_url="https://platform.example")
    # 3 evidence items supplied, well under the 5-item cap — all should appear.
    assert "authentication: app/auth/login.py" in comment
    assert "...and" not in comment  # no remainder note when under the cap


def test_risk_comment_never_includes_full_rationale_narrative():
    """The core no-full-model-output guarantee for the risk half of the comment."""
    comment = build_risk_comment(repo_id="repo-1", risk_output=_RISK_OUTPUT, platform_url="https://platform.example")
    assert _RISK_OUTPUT["rationale"] not in comment
    assert "very long multi-paragraph narrative" not in comment


def test_test_intelligence_comment_includes_concise_recommendations_and_link():
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=_TEST_OUTPUT, platform_url="https://platform.example"
    )
    assert "3 test suggestion(s)" in comment
    # Each recommendation: test_type + a short evidence-derived summary.
    assert "**unit**: source/diff content was supplied" in comment
    assert "**unit**: code defines or changes a route or response model" in comment
    assert "**negative**: code references authentication/authorization/secret handling" in comment
    assert "https://platform.example/repositories/repo-1/test-suggestions" in comment


def test_test_intelligence_comment_includes_confidence():
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=_TEST_OUTPUT, platform_url="https://platform.example"
    )
    assert "0.82" in comment
    assert "0.71" in comment
    assert "0.65" in comment


def test_test_intelligence_comment_never_includes_full_proposed_test_source():
    """The core no-full-model-output guarantee for the test-suggestion half."""
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=_TEST_OUTPUT, platform_url="https://platform.example"
    )
    for suggestion in _TEST_OUTPUT["suggestions"]:
        assert suggestion["proposed_test"] not in comment
    assert "def test_" not in comment  # no generated function signatures at all


def test_test_intelligence_comment_never_includes_full_rationale():
    """Recommendations are derived from `evidence`, not the full `rationale`
    paragraph — this asserts none of the long rationale text leaks through.
    """
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=_TEST_OUTPUT, platform_url="https://platform.example"
    )
    for suggestion in _TEST_OUTPUT["suggestions"]:
        assert suggestion["rationale"] not in comment
    assert "far too long to ever post" not in comment
    assert "should never appear verbatim" not in comment


def test_test_intelligence_comment_never_includes_assumptions():
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=_TEST_OUTPUT, platform_url="https://platform.example"
    )
    assert "Assumes the supplied code reflects the final version" not in comment


def test_test_intelligence_comment_caps_recommendations_and_notes_remainder():
    many_suggestions = {
        "suggestions": [{"test_type": "unit", "evidence": [f"signal number {i}"], "confidence": 0.5} for i in range(12)]
    }
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=many_suggestions, platform_url="https://platform.example"
    )
    # 5-item cap: only the first 5 signals should appear as bullet lines.
    assert "signal number 0" in comment
    assert "signal number 4" in comment
    assert "signal number 5" not in comment
    assert "signal number 11" not in comment
    assert "...and 7 more" in comment


def test_test_intelligence_comment_truncates_long_evidence_and_rationale_fallback():
    long_text = "x" * 500
    suggestion = {"suggestions": [{"test_type": "unit", "evidence": [long_text], "confidence": 0.5}]}
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=suggestion, platform_url="https://platform.example"
    )
    assert long_text not in comment
    assert "x" * 101 not in comment  # no run of the raw text exceeding the cap survives

    # Fallback path: no evidence at all, only a long rationale.
    suggestion_no_evidence = {
        "suggestions": [{"test_type": "unit", "evidence": [], "rationale": long_text, "confidence": 0.5}]
    }
    comment2 = build_test_intelligence_comment(
        repo_id="repo-1", test_output=suggestion_no_evidence, platform_url="https://platform.example"
    )
    assert long_text not in comment2


def test_test_intelligence_comment_stays_bounded_in_size_regardless_of_suggestion_count():
    """Comment size must not scale with the number of suggestions past the
    cap — this is what actually keeps PR comments scannable.
    """
    huge_output = {
        "suggestions": [
            {
                "test_type": "unit",
                "evidence": [f"evidence for suggestion {i} " + "detail " * 20],
                "rationale": "y" * 1000,
                "confidence": 0.5,
            }
            for i in range(200)
        ]
    }
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output=huge_output, platform_url="https://platform.example"
    )
    assert len(comment) < 2000


def test_test_intelligence_comment_handles_no_suggestions():
    comment = build_test_intelligence_comment(
        repo_id="repo-1", test_output={"suggestions": []}, platform_url="https://platform.example"
    )
    assert "No additional test coverage suggested" in comment


def test_test_intelligence_comment_notes_generation_failure():
    comment = build_test_intelligence_comment(
        repo_id="repo-1",
        test_output={"suggestions": [], "generation_failed": True},
        platform_url="https://platform.example",
    )
    assert "did not complete successfully" in comment


def test_pr_comment_combines_risk_and_test_sections_with_separator():
    comment = build_pr_comment(
        repo_id="repo-1", platform_url="https://platform.example", risk_output=_RISK_OUTPUT, test_output=_TEST_OUTPUT
    )
    assert "Risk Analysis" in comment
    assert "Recommended Tests" in comment
    assert "\n\n---\n\n" in comment


def test_pr_comment_omits_test_section_when_not_triggered():
    comment = build_pr_comment(
        repo_id="repo-1", platform_url="https://platform.example", risk_output=_RISK_OUTPUT, test_output=None
    )
    assert "Risk Analysis" in comment
    assert "Recommended Tests" not in comment
