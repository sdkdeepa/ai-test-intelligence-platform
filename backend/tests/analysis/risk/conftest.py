import pytest
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base, build_engine


@pytest.fixture
def session_factory():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
