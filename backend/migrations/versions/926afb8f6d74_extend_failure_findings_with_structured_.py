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
    """Downgrade schema.

    Re-adding `test_result_id NOT NULL` here is intentionally left as a
    strict, fail-loud operation, not softened with a data migration. On any
    database containing a `FailureFinding` row with `test_result_id IS NULL`
    — which is normal, legitimate data once the Failure Intelligence Engine
    is in real use (Sprint 8's design: it analyzes raw failure text that may
    have no corresponding persisted TestResult row, and correctly leaves
    test_result_id unset in that case) — this ALTER COLUMN will raise
    NotNullViolation and abort the downgrade. That's correct, not a bug:

    - The old (NOT NULL) and new (nullable) schemas encode genuinely
      different invariants. A NULL test_result_id has no valid
      representation in the old schema.
    - The only ways to make the downgrade "succeed" on such data are
      destructive: delete the rows that don't fit (silently discards real
      analysis results) or backfill them with a fabricated placeholder
      TestResult (worse — invents a false reference that never happened).
      Neither is implemented here, and neither should be added without an
      operator explicitly choosing and understanding that trade-off at the
      time they need it.
    - A loud failure forces exactly that decision to be made consciously,
      by a human, on the data in front of them — which is safer than this
      migration silently guessing on their behalf.

    Downgrading past this revision is therefore only unconditionally safe on
    a database with no such rows (e.g. a fresh/disposable one, as the
    PostgreSQL integration suite now uses — see
    tests/persistence/postgres/conftest.py). On a real, in-use database,
    handling those rows (export, delete, or otherwise) is a deliberate
    operational decision that belongs outside this migration, not inside it.
    """
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
