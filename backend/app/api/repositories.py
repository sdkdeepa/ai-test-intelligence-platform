import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.persistence.database import get_session
from app.persistence.models import Repository as RepositoryModel
from app.persistence.repositories import RepositoryRepository

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    default_branch: str = Field(default="main", min_length=1, max_length=200)


class RepositoryOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    default_branch: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[RepositoryOut])
def list_repositories(include_archived: bool = False, session: Session = Depends(get_session)) -> list:
    return RepositoryRepository(session).list(include_archived=include_archived)


@router.post("", response_model=RepositoryOut, status_code=201)
def create_repository(payload: RepositoryCreate, session: Session = Depends(get_session)) -> RepositoryModel:
    repos = RepositoryRepository(session)
    if repos.get_by_url(payload.url) is not None:
        raise HTTPException(status_code=409, detail="a repository with this url is already registered")

    repo = repos.add(RepositoryModel(name=payload.name, url=payload.url, default_branch=payload.default_branch))
    try:
        session.commit()
    except IntegrityError as exc:
        # Sprint 14 hardening: the check above is a courtesy for the common
        # case (a fast, friendly 409 without touching the DB's own
        # constraint), not the actual enforcement — two concurrent requests
        # can both pass `get_by_url() is None` before either commits. The
        # `repositories.url` unique constraint (migration 749e9896a218) is
        # what actually prevents the duplicate; this just turns that
        # constraint violation into the same clean 409 instead of an
        # unhandled 500.
        session.rollback()
        raise HTTPException(status_code=409, detail="a repository with this url is already registered") from exc
    return repo


@router.get("/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> RepositoryModel:
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return repo


@router.post("/{repo_id}/archive", response_model=RepositoryOut)
def archive_repository(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> RepositoryModel:
    """Soft-delete, not a hard `DELETE` — see `Repository`'s docstring in
    models.py for why. Idempotent: archiving an already-archived repository
    just succeeds again rather than erroring, since the caller's intent
    ("this repo should not be active") is already satisfied either way.
    """
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    repo.is_active = False
    session.commit()
    return repo


@router.post("/{repo_id}/unarchive", response_model=RepositoryOut)
def unarchive_repository(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> RepositoryModel:
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    repo.is_active = True
    session.commit()
    return repo
