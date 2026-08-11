"""One-off: create all tables for a throwaway database, driven entirely by
DATABASE_URL (see persistence/config.py). Used by the frontend's Playwright
e2e suite to stand up a real backend against a disposable SQLite file
instead of Alembic-migrating a full Postgres instance just for UI tests —
Base.metadata.create_all() is equivalent schema-wise and much faster to
throw away between runs.
"""

from app.persistence import models  # noqa: F401 — populates Base.metadata as a side effect of import
from app.persistence.database import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
