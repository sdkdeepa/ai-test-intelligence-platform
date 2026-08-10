"""extend failure findings with structured assessment fields

Revision ID: 926afb8f6d74
Revises: fc97630b89c5
Create Date: 2026-08-10 02:28:38.065421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '926afb8f6d74'
down_revision: Union[str, Sequence[str], None] = 'fc97630b89c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default added by hand, same rationale as prior migrations: safe
    # against a table with existing rows. ORM-level Python defaults in
    # models.py cover new inserts.
    op.add_column('failure_findings', sa.Column('test_case_id', sa.Uuid(), nullable=True))
    op.add_column('failure_findings', sa.Column('root_cause_hypotheses', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('failure_findings', sa.Column('evidence', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('failure_findings', sa.Column('missing_evidence', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('failure_findings', sa.Column('debugging_recommendations', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('failure_findings', sa.Column('suggested_bug_report', sa.Text(), nullable=True))

    # Batch mode (hand-added — autogenerate doesn't emit it): SQLite can't
    # ALTER COLUMN or ADD CONSTRAINT on an existing table directly, only via
    # a full table rebuild, which batch mode does transparently. Postgres
    # runs these as plain ALTER TABLE statements either way, so batch mode
    # is safe/portable for both dialects.
    with op.batch_alter_table('failure_findings') as batch_op:
        batch_op.alter_column('test_result_id', existing_type=sa.Uuid(), nullable=True)
        batch_op.create_index(
            batch_op.f('ix_failure_findings_test_case_id'), ['test_case_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_failure_findings_test_case_id_test_cases', 'test_cases', ['test_case_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('failure_findings') as batch_op:
        batch_op.drop_constraint('fk_failure_findings_test_case_id_test_cases', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_failure_findings_test_case_id'))
        batch_op.alter_column('test_result_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_column('failure_findings', 'suggested_bug_report')
    op.drop_column('failure_findings', 'debugging_recommendations')
    op.drop_column('failure_findings', 'missing_evidence')
    op.drop_column('failure_findings', 'evidence')
    op.drop_column('failure_findings', 'root_cause_hypotheses')
    op.drop_column('failure_findings', 'test_case_id')
