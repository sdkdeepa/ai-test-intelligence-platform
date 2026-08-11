"""Cross-engine analysis run history and per-run LLM invocation detail.

Generic across all three engines (unlike risk.py/test_intelligence.py/
failure_intelligence.py's own single-run status endpoint, kept where it is
for now to avoid an unrelated refactor) — this is what powers the dashboard's
Analysis Run History view: run status/timing plus the provider/model/
latency/token-usage detail LLMInvocation already captures (Sprint 9).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.persistence.database import get_session
from app.persistence.repositories import AnalysisRunRepository, LLMInvocationRepository, RepositoryRepository

router = APIRouter(prefix="/api/v1/repositories", tags=["analysis-runs"])


class AnalysisRunOut(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    type: str
    trigger: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class LLMInvocationOut(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    request_id: str | None
    estimated_cost: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/{repo_id}/analysis-runs", response_model=list[AnalysisRunOut])
def list_analysis_runs(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    if RepositoryRepository(session).get(repo_id) is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return AnalysisRunRepository(session).list_by_repo(repo_id)


@router.get("/{repo_id}/analysis-runs/{run_id}/llm-invocations", response_model=list[LLMInvocationOut])
def list_llm_invocations(repo_id: uuid.UUID, run_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    run = AnalysisRunRepository(session).get(run_id)
    if run is None or run.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return LLMInvocationRepository(session).list_by_run(run_id)
