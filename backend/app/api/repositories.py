import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.persistence.database import get_session
from app.persistence.models import Repository as RepositoryModel
from app.persistence.repositories import RepositoryRepository

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


class RepositoryCreate(BaseModel):
    name: str
    url: str
    default_branch: str = "main"


class RepositoryOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    default_branch: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[RepositoryOut])
def list_repositories(session: Session = Depends(get_session)) -> list:
    return RepositoryRepository(session).list()


@router.post("", response_model=RepositoryOut, status_code=201)
def create_repository(payload: RepositoryCreate, session: Session = Depends(get_session)) -> RepositoryModel:
    repos = RepositoryRepository(session)
    if repos.get_by_url(payload.url) is not None:
        raise HTTPException(status_code=409, detail="a repository with this url is already registered")

    repo = repos.add(RepositoryModel(name=payload.name, url=payload.url, default_branch=payload.default_branch))
    session.commit()
    return repo


@router.get("/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: uuid.UUID, session: Session = Depends(get_session)) -> RepositoryModel:
    repo = RepositoryRepository(session).get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return repo
