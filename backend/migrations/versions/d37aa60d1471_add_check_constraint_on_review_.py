"""add check constraint on review_requests.status

Revision ID: d37aa60d1471
Revises: 4cbca7bf6553
Create Date: 2026-08-11 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd37aa60d1471'
down_revision: Union[str, Sequence[str], None] = '4cbca7bf6553'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sprint 14 hardening: close the gap between what the ORM model now
    declares (`ReviewRequest.__table_args__`'s CheckConstraint, added in the
    same commit as this migration) and what the schema on disk actually
    enforces. `batch_alter_table` is used rather than a bare `op.create_check
    _constraint` so this migration works unmodified against both SQLite
    (which has no native ALTER TABLE ADD CONSTRAINT and needs the
    recreate-and-copy strategy batch mode implements) and PostgreSQL (where
    batch mode transparently falls back to a plain ALTER TABLE).
    """
    with op.batch_alter_table("review_requests") as batch_op:
        batch_op.create_check_constraint(
            "ck_review_requests_status", "status IN ('pending', 'approved', 'rejected')"
        )


def downgrade() -> None:
    with op.batch_alter_table("review_requests") as batch_op:
        batch_op.drop_constraint("ck_review_requests_status", type_="check")
