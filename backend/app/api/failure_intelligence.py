"""The Failure Intelligence Engine's HTTP surface: trigger analysis, read
findings. Same vertical-slice shape as app/api/risk.py and
app/api/test_intelligence.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.orchestration.bootstrap import get_orchestrator
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.registry import EngineNotRegisteredError
from app.persistence.database import get_session
from app.persistence.repositories import FailureFindingRepository, RepositoryRepository

router = APIRouter(prefix="/api/v1/repositories", tags=["failure-intelligence"])


class FailureIntelligenceRequest(BaseModel):
    pytest_output: str | None = None
    playwright_output: str | None = None
    stack_trace: str | None = None
    ci_log: str | None = None
    application_log: str | None = None
    environment_info: str | None = None
    test_name: str | None = None
    test_case_id: uuid.UUID | None = None
    trigger: str = "manual"


class FailureIntelligenceTriggered(BaseModel):
    analysis_run_id: uuid.UUID
    status: str


class FailureFindingOut(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    test_result_id: uuid.UUID | None
    test_case_id: uuid.UUID | None
    classification: str
    confidence_score: float | None
    rationale: str | None
    root_cause_hypotheses: list[str]
    evidence: list[str]
    missing_evidence: list[str]
    debugging_recommendations: list[str]
    suggested_bug_report: str | None

    model_config = {"from_attributes": True}


@router.post("/{repo_id}/failure-intelligence", response_model=FailureIntelligenceTriggered, status_code=202)
def trigger_failure_intelligence(
    repo_id: uuid.UUID,
    payload: FailureIntelligenceRequest,
    session: Session = Depends(get_session),
    orchestrator: AnalysisOrchestrator = Depends(get_orchestrator),
) -> FailureIntelligenceTriggered:
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    if not repo.is_active:
        raise HTTPException(status_code=409, detail="repository is archived and cannot accept new analysis")

    try:
        analysis_run_id = orchestrator.submit(
            repo_id=repo_id,
            engine_type="failure_intelligence",
            trigger=payload.trigger,
            inputs={
                "pytest_output": payload.pytest_output,
                "playwright_output": payload.playwright_output,
                "stack_trace": payload.stack_trace,
                "ci_log": payload.ci_log,
                "application_log": payload.application_log,
                "environment_info": payload.environment_info,
                "test_name": payload.test_name,
                "test_case_id": payload.test_case_id,
            },
        )
    except EngineNotRegisteredError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FailureIntelligenceTriggered(analysis_run_id=analysis_run_id, status="pending")


@router.get("/{repo_id}/failure-findings", response_model=list[FailureFindingOut])
def list_failure_findings(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    return FailureFindingRepository(session).list_by_repo(repo_id)
