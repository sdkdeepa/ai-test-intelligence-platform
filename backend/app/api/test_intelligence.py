"""The Test Intelligence Engine's HTTP surface: trigger analysis, read
suggestions, accept/reject them. Same vertical-slice shape as app/api/risk.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.orchestration.bootstrap import get_orchestrator
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.registry import EngineNotRegisteredError
from app.persistence.database import get_session
from app.persistence.models import TestSuggestion
from app.persistence.repositories import RepositoryRepository, TestSuggestionRepository

repo_router = APIRouter(prefix="/api/v1/repositories", tags=["test-intelligence"])
suggestion_router = APIRouter(prefix="/api/v1/test-suggestions", tags=["test-intelligence"])


class TestIntelligenceRequest(BaseModel):
    source_code: str | None = None
    requirement_text: str | None = None
    api_specification: str | None = None
    diff: str | None = None
    existing_test_context: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    pr_number: int | None = None
    trigger: str = "manual"


class TestIntelligenceTriggered(BaseModel):
    analysis_run_id: uuid.UUID
    status: str


class TestSuggestionOut(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    repo_id: uuid.UUID
    file_path: str
    target_function: str | None
    suggested_test_code: str
    rationale: str | None
    status: str
    test_type: str
    evidence: list[str]
    assumptions: list[str]
    confidence: float
    uncovered_risks: list[str]
    recommended_follow_up_validation: list[str]

    model_config = {"from_attributes": True}


@repo_router.post("/{repo_id}/test-intelligence", response_model=TestIntelligenceTriggered, status_code=202)
def trigger_test_intelligence(
    repo_id: uuid.UUID,
    payload: TestIntelligenceRequest,
    session: Session = Depends(get_session),
    orchestrator: AnalysisOrchestrator = Depends(get_orchestrator),
) -> TestIntelligenceTriggered:
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    if not repo.is_active:
        raise HTTPException(status_code=409, detail="repository is archived and cannot accept new analysis")

    try:
        analysis_run_id = orchestrator.submit(
            repo_id=repo_id,
            engine_type="test_intelligence",
            trigger=payload.trigger,
            commit_sha=payload.commit_sha,
            pr_number=payload.pr_number,
            inputs={
                "source_code": payload.source_code,
                "requirement_text": payload.requirement_text,
                "api_specification": payload.api_specification,
                "diff": payload.diff,
                "existing_test_context": payload.existing_test_context,
                "file_path": payload.file_path,
            },
        )
    except EngineNotRegisteredError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TestIntelligenceTriggered(analysis_run_id=analysis_run_id, status="pending")


@repo_router.get("/{repo_id}/test-suggestions", response_model=list[TestSuggestionOut])
def list_test_suggestions(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    return TestSuggestionRepository(session).list_by_repo(repo_id)


def _set_status(suggestion_id: uuid.UUID, status: str, session: Session) -> TestSuggestion:
    repo = TestSuggestionRepository(session)
    suggestion = repo.get(suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="test suggestion not found")
    suggestion.status = status
    session.commit()
    session.refresh(suggestion)
    return suggestion


@suggestion_router.post("/{suggestion_id}/accept", response_model=TestSuggestionOut)
def accept_test_suggestion(suggestion_id: uuid.UUID, session: Session = Depends(get_session)) -> TestSuggestion:
    return _set_status(suggestion_id, "accepted", session)


@suggestion_router.post("/{suggestion_id}/reject", response_model=TestSuggestionOut)
def reject_test_suggestion(suggestion_id: uuid.UUID, session: Session = Depends(get_session)) -> TestSuggestion:
    return _set_status(suggestion_id, "rejected", session)
