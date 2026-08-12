"""add unique constraint on repositories.url

Revision ID: 749e9896a218
Revises: d37aa60d1471
Create Date: 2026-08-11 11:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '749e9896a218'
down_revision: Union[str, Sequence[str], None] = 'd37aa60d1471'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sprint 14 hardening — see Repository's docstring in models.py for why
    this closes a real (if narrow) bug: `RepositoryRepository.get_by_url()`
    always assumed at most one row per URL, but nothing enforced that until
    now. `batch_alter_table` for the same SQLite/PostgreSQL portability
    reason as d37aa60d1471.

    Note for operators: if any *existing* database already has duplicate
    `repositories.url` values, this migration will fail — that's
    intentional (surfacing pre-existing bad data rather than silently
    picking one row to keep), and those duplicates need resolving by hand
    before upgrading past this revision.
    """
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.create_unique_constraint("uq_repositories_url", ["url"])


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.drop_constraint("uq_repositories_url", type_="unique")
