"""add review requests and audit events

Revision ID: 4cbca7bf6553
Revises: 926afb8f6d74
Create Date: 2026-08-11 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cbca7bf6553'
down_revision: Union[str, Sequence[str], None] = '926afb8f6d74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'review_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('analysis_run_id', sa.Uuid(), nullable=False),
        sa.Column('repo_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('reasons', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('risk_summary', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('github_owner', sa.String(), nullable=True),
        sa.Column('github_repo', sa.String(), nullable=True),
        sa.Column('github_head_sha', sa.String(), nullable=True),
        sa.Column('github_pr_number', sa.Integer(), nullable=True),
        sa.Column('reviewer', sa.String(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['repo_id'], ['repositories.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_review_requests_analysis_run_id'), 'review_requests', ['analysis_run_id'], unique=False)
    op.create_index(op.f('ix_review_requests_repo_id'), 'review_requests', ['repo_id'], unique=False)

    op.create_table(
        'audit_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('review_request_id', sa.Uuid(), nullable=True),
        sa.Column('analysis_run_id', sa.Uuid(), nullable=True),
        sa.Column('repo_id', sa.Uuid(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['review_request_id'], ['review_requests.id']),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['repo_id'], ['repositories.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_events_review_request_id'), 'audit_events', ['review_request_id'], unique=False)
    op.create_index(op.f('ix_audit_events_analysis_run_id'), 'audit_events', ['analysis_run_id'], unique=False)
    op.create_index(op.f('ix_audit_events_repo_id'), 'audit_events', ['repo_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Straightforward drop, unlike 926afb8f6d74's downgrade: both tables are
    wholly new in this revision (no prior schema shape to reconcile with),
    so there's no data-loss judgment call to make here the way there was for
    that migration's NOT NULL tightening — dropping these tables always
    means "discard every review decision and audit event ever recorded",
    which is inherent to reverting past this revision, not a choice this
    migration is making on an operator's behalf.
    """
    op.drop_index(op.f('ix_audit_events_repo_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_analysis_run_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_review_request_id'), table_name='audit_events')
    op.drop_table('audit_events')

    op.drop_index(op.f('ix_review_requests_repo_id'), table_name='review_requests')
    op.drop_index(op.f('ix_review_requests_analysis_run_id'), table_name='review_requests')
    op.drop_table('review_requests')
