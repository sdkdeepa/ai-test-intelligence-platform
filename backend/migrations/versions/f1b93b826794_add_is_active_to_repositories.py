"""add is_active to repositories

Revision ID: f1b93b826794
Revises: 749e9896a218
Create Date: 2026-08-12 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b93b826794'
down_revision: Union[str, Sequence[str], None] = '749e9896a218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Soft-delete support for repositories (see Repository's docstring in
    models.py for why this is a flag, not a DELETE endpoint). `server_default
    'true'` matters here, not just the ORM-level Python default: every
    existing row at migration time needs a real value, and every row
    inserted through any path other than the ORM (a script, a manual
    fixture load) still gets a sane default rather than a null-constraint
    violation.
    """
    op.add_column(
        "repositories",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("repositories", "is_active")
