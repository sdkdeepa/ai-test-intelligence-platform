"""The Risk Engine's HTTP surface: trigger analysis, check run status, read
findings. This is the last leg of the vertical slice — request -> `submit()`
-> TaskQueue -> RiskEngine -> provider -> persistence -> this router reading
it back out.
"""

import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session_factory
from app.governance.review_service import evaluate_and_maybe_create_review_request
from app.orchestration.bootstrap import get_orchestrator
from app.orchestration.engine import AnalysisResult
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.registry import EngineNotRegisteredError
from app.persistence.database import get_session
from app.persistence.repositories import AnalysisRunRepository, RepositoryRepository, RiskFindingRepository

router = APIRouter(prefix="/api/v1/repositories", tags=["risk"])


class RiskAnalysisRequest(BaseModel):
    diff: str
    commit_sha: str | None = None
    pr_number: int | None = None
    trigger: str = "manual"


class RiskAnalysisTriggered(BaseModel):
    analysis_run_id: uuid.UUID
    status: str


class AnalysisRunOut(BaseModel):
    analysis_run_id: uuid.UUID
    status: str


class RiskFindingOut(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    file_path: str
    risk_score: float
    rationale: str | None
    categories: list[str]
    evidence: list[str]
    confidence_score: float
    affected_components: list[str]
    recommended_regression_scope: list[str]
    release_recommendation: str

    model_config = {"from_attributes": True}


@router.post("/{repo_id}/risk-analysis", response_model=RiskAnalysisTriggered, status_code=202)
def trigger_risk_analysis(
    repo_id: uuid.UUID,
    payload: RiskAnalysisRequest,
    session: Session = Depends(get_session),
    orchestrator: AnalysisOrchestrator = Depends(get_orchestrator),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> RiskAnalysisTriggered:
    if RepositoryRepository(session).get(repo_id) is None:
        raise HTTPException(status_code=404, detail="repository not found")

    def _on_result(analysis_run_id: uuid.UUID, result: AnalysisResult) -> None:
        # Sprint 13: governance runs for every completed risk assessment
        # regardless of trigger, manual API calls included — not just
        # webhook-originated ones — so the dashboard's pending-approvals
        # view reflects every risk run that needs a human look, not only
        # the ones that happened to arrive via GitHub. See
        # governance/review_service.py's module docstring.
        if result.status != "completed" or not isinstance(result.output, dict):
            return
        gov_session = session_factory()
        try:
            evaluate_and_maybe_create_review_request(
                gov_session, analysis_run_id=analysis_run_id, repo_id=repo_id, risk_output=result.output
            )
            gov_session.commit()
        finally:
            gov_session.close()

    try:
        analysis_run_id = orchestrator.submit(
            repo_id=repo_id,
            engine_type="risk",
            trigger=payload.trigger,
            commit_sha=payload.commit_sha,
            pr_number=payload.pr_number,
            inputs={"diff": payload.diff},
            on_result=_on_result,
        )
    except EngineNotRegisteredError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RiskAnalysisTriggered(analysis_run_id=analysis_run_id, status="pending")


@router.get("/{repo_id}/analysis-runs/{run_id}", response_model=AnalysisRunOut)
def get_analysis_run(repo_id: uuid.UUID, run_id: uuid.UUID, session: Session = Depends(get_session)) -> AnalysisRunOut:
    run = AnalysisRunRepository(session).get(run_id)
    if run is None or run.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return AnalysisRunOut(analysis_run_id=run.id, status=run.status)


@router.get("/{repo_id}/risk-findings", response_model=list[RiskFindingOut])
def list_risk_findings(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    return RiskFindingRepository(session).list_by_repo(repo_id)
