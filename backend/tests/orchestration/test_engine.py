import uuid

import pytest

from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult


def test_analysis_engine_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        AnalysisEngine()


def test_analysis_context_carries_engine_agnostic_inputs():
    context = AnalysisContext(
        analysis_run_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        trigger="pr",
        engine_type="risk",
        inputs={"changed_files": ["app/main.py"]},
        correlation_id="corr-1",
        trace_id="trace-1",
    )

    assert context.inputs == {"changed_files": ["app/main.py"]}
    assert context.commit_sha is None


def test_analysis_result_defaults_to_no_error():
    result = AnalysisResult(status="completed", output={"score": 0.5})

    assert result.error is None


def test_analysis_result_failed_status_carries_error():
    result = AnalysisResult(status="failed", error="no test files found")

    assert result.status == "failed"
    assert result.error == "no test files found"
